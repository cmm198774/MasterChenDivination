import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from contextlib import asynccontextmanager
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
import uvicorn
from sys_logger import setup_global_logger
from MyTools import add_urls_to_db
from MyTools import get_voice
from config import (
    LLM_MODEL_NAME,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_TEMPERATURE,
    REDIS_URL,
    QDRANT_COLLECTION,
    SERVER_HOST,
    SERVER_PORT,
    THREAD_POOL_SIZE,
)
from start_redis import start_redis_server, stop_redis_server

# 全局 logger（启动阶段使用，清空之前的日志）
global_logger = setup_global_logger(clear_previous_logs=True)

# 全局 Master 实例
master_instance = None

# 全局线程池
executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，启动 Redis 和 Master 实例"""
    global master_instance

    # 启动 Redis 服务器
    global_logger.info("启动 Redis 服务器...")
    start_redis_server()

    # 创建 Master 实例（使用 RedisSaver）
    global_logger.info("创建 Master 实例...")
    master_instance = Master()
    global_logger.info("Master 实例创建完成")

    yield

    # 关闭 Redis 服务器
    global_logger.info("关闭 Redis 服务器...")
    stop_redis_server()
    global_logger.info("应用关闭")


app = FastAPI(lifespan=lifespan)
from MyTools import *
from MyAgent import create_agent_graph
from sys_memory import RedisSaver


class Master:
    def __init__(self):
        # 创建 RedisSaver
        redis_saver = RedisSaver(redis_url=REDIS_URL)

        # 初始化 LangGraph agent graph（启用情绪检测，使用 Redis 持久化）
        self.agent_graph = create_agent_graph(
            model_name=LLM_MODEL_NAME,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            temperature=LLM_TEMPERATURE,
            tool_list=[get_info_from_local_db, bazi_cesuan, yaoyigua, jiemeng],
            tool_descriptions=TOOL_DESCRIPTIONS,
            tool_timeout=20,
            enable_mood_detection=True,
            checkpointer=redis_saver,  # 使用 Redis 持久化
        )

    def run(self, query: str, user_id: str = "default"):
        global_logger.info(f"[{user_id}] 收到查询：{query}")

        # 用 graph.invoke 调用（情绪检测在 graph 内部自动完成）
        global_logger.debug(f"[{user_id}] 开始 agent 推理...")

        # 添加 config 参数，指定 thread_id
        config = {"configurable": {"thread_id": user_id}}

        # 添加 system prompt 作为第一条消息（只在第一次对话时添加）
        # MemorySaver 会保存历史，所以后续对话会自动包含之前的消息
        messages = [HumanMessage(content=query)]

        result = self.agent_graph.invoke({
            "messages": messages,
        }, config=config)

        # 调试：记录保存的消息数量
        global_logger.debug(f"[{user_id}] 当前保存的消息数：{len(result.get('messages', []))}")
        for i, msg in enumerate(result.get('messages', [])[-5:]):  # 仅显示最后5条消息
            content_str = str(msg.content)[:50] if hasattr(msg, 'content') else 'N/A'
            global_logger.debug(f"[{user_id}]   [{i}] {type(msg).__name__}: {content_str}...")

        qingxu = result.get("mood", "default")
        global_logger.debug(f"[{user_id}] 情绪：{qingxu}")
        messages = result.get("messages", [])
        if not messages:
            return {"input": query, "output": "No response generated", "qingxu": qingxu}
        last_message = messages[-1]
        return {"input": query, "output": last_message.content, "qingxu": qingxu}


# Master 实例已在 lifespan 中创建


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/chat")
async def chat(query: str, user_id: str = "default"):
    # 使用 lifespan 中创建的 master_instance
    if master_instance is None:
        return {"error": "Master 实例未初始化"}

    # 在线程池中执行同步的 run()
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(
        executor,
        partial(master_instance.run, query, user_id=user_id)
    )

    # Generate voice_id and add to response
    timestamp_ms = int(time.time() * 1000)
    voice_id = f"{user_id}_{timestamp_ms}"
    res["voice_id"] = voice_id

    return res


@app.post("/get_audio")
async def get_audio(voice_id: str, text: str, mood: str = "default"):
    """
    生成并返回音频。

    Args:
        voice_id: 音频ID
        text: 要转换的文本
        mood: 情绪（default/upbeat/angry/depressed/friendly/cheerful）

    Returns:
        Response: 音频数据（WAV 格式）
    """
    from fastapi.responses import Response
    from fastapi import HTTPException

    global_logger.info(f"生成音频: voice_id={voice_id}, mood={mood}, text={text[:50]}...")

    # 在线程池中执行同步的 get_voice()
    loop = asyncio.get_running_loop()
    audio_bytes = await loop.run_in_executor(
        executor,
        partial(get_voice, text, mood)
    )

    if audio_bytes is None:
        raise HTTPException(status_code=500, detail="Failed to generate audio")

    global_logger.info(f"音频生成成功: {len(audio_bytes)} bytes")

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f"attachment; filename={voice_id}.wav"}
    )


@app.post("/add_urls")
def add_urls(urls: list[str]):
    """
    添加 URL 到 RAG 数据库。

    Args:
        urls: URL 列表（本地路径或远程 URL）

    Returns:
        dict: 处理结果
    """

    global_logger.info(f"收到添加 URL 请求: {len(urls)} 个")

    try:
        result = add_urls_to_db(urls, collection_name=QDRANT_COLLECTION)
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        global_logger.error(f"添加 URL 失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/add_pdfs")
def add_pdfs():
    return {"response": "pdfs added successfully."}


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
