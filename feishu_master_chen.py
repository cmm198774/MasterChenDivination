"""
飞书前端 - 陈大师
通过飞书 WebSocket 长连接接收消息，转发到 server.py 处理，
返回文本和语音回复。

核心架构（方案 A：线程池 + 每用户队列）：
1. WebSocket 接收飞书消息 → 按用户路由到对应队列
2. 每个用户有独立的 Worker 线程，保证消息顺序处理
3. 线程池限制最大并发用户数（FEISHU_MAX_USERS，默认 50）
4. 用户不活跃超时后自动清理（FEISHU_USER_TIMEOUT，默认 300 秒）

优势：
- 同一用户的消息按顺序处理（保持对话上下文）
- 不同用户的消息并行处理（提高并发能力）
- 线程数可控（防止资源爆炸）
"""
import os
import sys
import ssl

# 修复 Windows SSL 证书问题：跳过损坏的 Windows 证书存储，使用 certifi 证书
if sys.platform == "win32":
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    except ImportError:
        pass
    if hasattr(ssl.SSLContext, "_load_windows_store_certs"):
        ssl.SSLContext._load_windows_store_certs = lambda self, storename, purpose: None

import json
import time
import queue
import threading
import subprocess
import io
import requests
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    CreateMessageRequest,
    CreateMessageRequestBody,
    CreateFileRequest,
    CreateFileRequestBody,
)
from pydub import AudioSegment
from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    SERVER_HOST,
    SERVER_PORT,
    CHAT_TIMEOUT,
    VOICE_TIMEOUT,
    FEISHU_MAX_USERS,
    FEISHU_USER_TIMEOUT,
)
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

# ============ 配置 ============
APP_ID = FEISHU_APP_ID
APP_SECRET = FEISHU_APP_SECRET

SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# ============ 全局变量 ============
# 每用户队列系统
user_queues = defaultdict(queue.Queue)  # {sender_id: Queue}
user_last_active = {}  # {sender_id: timestamp}
user_processing_lock = threading.Lock()  # 保护用户状态
active_workers = set()  # 正在处理的用户集合

# 线程池（限制并发数）
worker_pool = None  # 在 main() 中初始化

server_process = None
feishu_client = None


# ============ 服务器管理 ============
def start_server():
    """启动 server.py 作为子进程"""
    global server_process
    project_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(project_dir, "server.py")

    # 使用当前 Python 解释器运行（兼容不同环境）
    server_process = subprocess.Popen(
        [sys.executable, server_script],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    print(f"[Master Chen] server.py 已启动 (PID: {server_process.pid})")

    # 等待服务器就绪
    for i in range(20):
        time.sleep(1)
        try:
            resp = requests.get(f"{SERVER_URL}/", timeout=2)
            if resp.status_code == 200:
                print("[Master Chen] server.py 已就绪")
                return True
        except Exception:
            pass
        print(f"[Master Chen] 等待 server.py 启动... ({i+1}/20)")

    print("[Master Chen] server.py 启动超时")
    return False


def stop_server():
    """停止 server.py 子进程"""
    global server_process
    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("[Master Chen] server.py 已停止")
        server_process = None


# ============ 音频处理 ============
def convert_wav_to_opus(wav_data: bytes) -> bytes:
    """将 WAV 音频转换为 OPUS 格式"""
    audio = AudioSegment.from_file(io.BytesIO(wav_data), format="wav")
    opus_buffer = io.BytesIO()
    audio.export(opus_buffer, format="opus", codec="libopus")
    return opus_buffer.getvalue()


def upload_audio_to_feishu(opus_data: bytes, filename: str) -> str:
    """上传音频到飞书，返回 file_key"""
    request = CreateFileRequest.builder() \
        .request_body(CreateFileRequestBody.builder()
            .file_type("opus")
            .file_name(filename)
            .file(io.BytesIO(opus_data))
            .build()) \
        .build()

    response = feishu_client.im.v1.file.create(request)
    if response.success():
        return response.data.file_key
    else:
        print(f"[Master Chen] 上传音频失败: {response.code} - {response.msg}")
        return None


def send_audio_to_feishu(sender_id: str, file_key: str):
    """发送音频消息到飞书"""
    content = json.dumps({"file_key": file_key})

    request = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(sender_id)
            .msg_type("audio")
            .content(content)
            .build()
        ) \
        .build()

    response = feishu_client.im.v1.message.create(request)
    if response.success():
        print(f"[Master Chen] 音频消息发送成功")
    else:
        print(f"[Master Chen] 发送音频失败: {response.code} - {response.msg}")


def send_text_to_feishu(sender_id: str, text: str):
    """发送文本消息到飞书"""
    content = json.dumps({"text": text})

    request = CreateMessageRequest.builder() \
        .receive_id_type("open_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(sender_id)
            .msg_type("text")
            .content(content)
            .build()
        ) \
        .build()

    response = feishu_client.im.v1.message.create(request)
    if response.success():
        print(f"[Master Chen] 文本消息发送成功")
    else:
        print(f"[Master Chen] 发送文本失败: {response.code} - {response.msg}")


# ============ 消息处理 ============
def process_message(sender_id: str, text: str):
    """处理单条消息的完整流程"""
    print(f"\n[Master Chen] 处理消息: sender={sender_id}, text={text[:50]}...")

    # Step 1: POST /chat
    try:
        resp = requests.post(f"{SERVER_URL}/chat", params={"query": text}, timeout=CHAT_TIMEOUT)
        if resp.status_code != 200:
            send_text_to_feishu(sender_id, f"服务异常: HTTP {resp.status_code}")
            return
        result = resp.json()
    except Exception as e:
        send_text_to_feishu(sender_id, f"服务连接失败: {e}")
        return

    output_text = result.get("output", "")
    voice_id = result.get("voice_id", "")
    qingxu = result.get("qingxu", "default")

    # Step 2: 发送文本回复
    send_text_to_feishu(sender_id, output_text)

    # Step 3: 获取音频
    if not voice_id:
        print("[Master Chen] 没有 voice_id，跳过音频")
        return

    try:
        audio_resp = requests.post(
            f"{SERVER_URL}/get_audio",
            params={
                "voice_id": voice_id,
                "text": output_text,
                "mood": qingxu,
            },
            timeout=VOICE_TIMEOUT + 10,
        )
        if audio_resp.status_code != 200:
            print(f"[Master Chen] 获取音频失败: HTTP {audio_resp.status_code}")
            return

        wav_data = audio_resp.content
        print(f"[Master Chen] 获取音频: {len(wav_data)} bytes")
    except Exception as e:
        print(f"[Master Chen] 获取音频异常: {e}")
        return

    # Step 4: 转换 WAV → OPUS
    try:
        opus_data = convert_wav_to_opus(wav_data)
        print(f"[Master Chen] 转换完成: {len(opus_data)} bytes")
    except Exception as e:
        print(f"[Master Chen] 音频转换失败: {e}")
        return

    # Step 5: 上传并发送音频
    file_key = upload_audio_to_feishu(opus_data, f"{voice_id}.opus")
    if file_key:
        send_audio_to_feishu(sender_id, file_key)


def user_worker(sender_id: str):
    """
    用户专属 Worker：处理单个用户的所有消息
    保证同一用户的消息按顺序处理
    """
    print(f"[Master Chen] 用户 Worker 启动: {sender_id[:10]}...")

    while True:
        try:
            # 从该用户的队列取消息（阻塞等待）
            text = user_queues[sender_id].get(timeout=FEISHU_USER_TIMEOUT)

            # 更新活跃时间
            with user_processing_lock:
                user_last_active[sender_id] = time.time()

            # 处理消息
            process_message(sender_id, text)

            # 标记任务完成
            user_queues[sender_id].task_done()

        except queue.Empty:
            # 超时，清理该用户的 Worker
            print(f"[Master Chen] 用户不活跃，清理 Worker: {sender_id[:10]}...")
            with user_processing_lock:
                if sender_id in active_workers:
                    active_workers.remove(sender_id)
                if sender_id in user_queues:
                    del user_queues[sender_id]
                if sender_id in user_last_active:
                    del user_last_active[sender_id]
            break

        except Exception as e:
            print(f"[Master Chen] 用户 Worker 异常: {sender_id[:10]}... - {e}")


# ============ 飞书事件处理 ============
def on_message_event(data: P2ImMessageReceiveV1) -> None:
    """处理飞书消息事件"""
    event = data.event
    message = event.message
    msg_type = message.message_type
    sender = event.sender
    sender_id = sender.sender_id.open_id

    # 只处理文本消息
    if msg_type != "text":
        return

    content = json.loads(message.content)
    text = content.get("text", "")

    if not text:
        return

    print(f"[Master Chen] 收到消息: sender={sender_id[:10]}..., text={text[:50]}...")

    # 检查并发限制
    with user_processing_lock:
        current_users = len(active_workers)

    if current_users >= FEISHU_MAX_USERS:
        print(f"[Master Chen] 并发已满（{current_users}/{FEISHU_MAX_USERS}），消息被丢弃")
        send_text_to_feishu(sender_id, "当前用户太多，请稍后再试")
        return

    # 首次消息：启动用户专属 Worker
    with user_processing_lock:
        if sender_id not in active_workers:
            active_workers.add(sender_id)
            user_last_active[sender_id] = time.time()

            # 提交到线程池
            worker_pool.submit(user_worker, sender_id)
            print(f"[Master Chen] 启动用户 Worker: {sender_id[:10]}... (当前并发: {len(active_workers)})")

    # 放入该用户的队列
    user_queues[sender_id].put(text)


# ============ 主程序 ============
def main():
    """启动飞书机器人"""
    global feishu_client, worker_pool

    print("=" * 60)
    print("[Master Chen] 飞书前端启动")
    print(f"[Master Chen] 配置: 最大并发={FEISHU_MAX_USERS}, 用户超时={FEISHU_USER_TIMEOUT}秒")
    print("=" * 60)

    # Step 1: 启动 server.py
    if not start_server():
        print("[Master Chen] server.py 启动失败，退出")
        return

    # Step 2: 创建飞书客户端
    feishu_client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .build()

    # Step 3: 初始化线程池
    worker_pool = ThreadPoolExecutor(max_workers=FEISHU_MAX_USERS)
    print(f"[Master Chen] 线程池初始化完成（最大线程数: {FEISHU_MAX_USERS}）")

    # Step 4: 启动飞书 WebSocket 长连接
    print("[Master Chen] 连接飞书 WebSocket...")

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message_event) \
        .build()

    ws_client = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    try:
        ws_client.start()
    except KeyboardInterrupt:
        print("\n[Master Chen] 正在关闭...")
    finally:
        worker_pool.shutdown(wait=True)
        stop_server()
        print("[Master Chen] 已退出")


if __name__ == "__main__":
    main()
