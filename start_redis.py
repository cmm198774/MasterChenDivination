"""
Redis 服务器管理模块
提供启动和停止 Redis 服务器的功能
"""
import atexit
import os
import subprocess
import time


# 全局变量，保存 Redis 进程
_redis_process = None


def start_redis_server():
    """
    启动 Redis 服务器

    Returns:
        subprocess.Popen: Redis 进程对象，如果已在运行则返回 None
    """
    global _redis_process

    # 检查是否已有 Redis 在运行（通过连接测试）
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.connect(("127.0.0.1", 6379))
        print("[Redis] 已在运行")
        sock.close()
        return None  # 已在运行，不需要启动新的
    except (ConnectionRefusedError, socket.timeout):
        pass  # Redis 未运行，需要启动
    finally:
        sock.close()

    # 项目目录
    project_dir = os.path.dirname(os.path.abspath(__file__))
    redis_exe = os.path.join(project_dir, "redis-server", "redis-server.exe")
    redis_conf = os.path.join(project_dir, "redis_cache", "redis.conf")
    redis_data_dir = os.path.join(project_dir, "redis_cache")

    # 创建 redis_cache 目录
    os.makedirs(redis_data_dir, exist_ok=True)

    # 创建配置文件
    if not os.path.exists(redis_conf):
        with open(redis_conf, 'w', encoding='utf-8') as f:
            f.write("""# Redis 配置文件
dir redis_cache
bind 127.0.0.1
port 6379
loglevel notice
""")
        print("[Redis] 创建 redis.conf")

    # 启动 Redis
    _redis_process = subprocess.Popen(
        [redis_exe, redis_conf],
        cwd=project_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[Redis] 服务器启动 (PID: {_redis_process.pid})")

    # 注册退出时自动关闭 Redis
    atexit.register(stop_redis_server)

    # 等待启动完成
    time.sleep(1)
    return _redis_process


def stop_redis_server():
    """停止 Redis 服务器"""
    global _redis_process
    if _redis_process and _redis_process.poll() is None:
        _redis_process.terminate()
        try:
            _redis_process.wait(timeout=3)
            print(f"[Redis] 服务器已停止 (PID: {_redis_process.pid})")
        except subprocess.TimeoutExpired:
            _redis_process.kill()
            print(f"[Redis] 强制停止 (PID: {_redis_process.pid})")
    _redis_process = None


def stop_redis_by_command():
    """
    通过系统命令强制关闭 Redis 服务器
    用于子进程场景（如 feishu_master_chen.py 关闭时）
    """
    try:
        subprocess.run(
            ["powershell", "-Command",
             "Get-Process -Name 'redis-server' -ErrorAction SilentlyContinue | Stop-Process -Force"],
            capture_output=True, timeout=5
        )
        print("[Redis] 服务器已关闭")
    except Exception as e:
        print(f"[Redis] 关闭失败: {e}")
