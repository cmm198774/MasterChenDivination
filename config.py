"""
全局配置模块
从 .env 文件加载所有 API 密钥和服务配置
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)


# ==========================================
# API 密钥
# ==========================================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
BAIDU_AI_SEARCH_API_KEY = os.getenv("BAIDU_AI_SEARCH_API_KEY", "")
YUANFENJU_API_KEY = os.getenv("YUANFENJU_API_KEY", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

# ==========================================
# 飞书机器人
# ==========================================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# ==========================================
# 服务配置
# ==========================================
# Docker 环境绑定 0.0.0.0，本地绑定 127.0.0.1
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0" if os.path.exists("/.dockerenv") else "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# LLM 模型配置
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen3.6-flash")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# TTS 语音配置
TTS_VOICE = os.getenv("TTS_VOICE", "Eldric Sage")
TTS_MODEL = os.getenv("TTS_MODEL", "qwen3-tts-instruct-flash")

# Embedding 配置
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# Qdrant 向量数据库
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "yunshi_2026")
# Docker 环境使用容器名，本地使用 localhost
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant" if os.path.exists("/.dockerenv") else "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_qdrand")

# Redis 配置
# Docker 环境使用容器名，本地使用 localhost
REDIS_HOST = os.getenv("REDIS_HOST", "redis" if os.path.exists("/.dockerenv") else "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"

# 线程池配置
THREAD_POOL_SIZE = int(os.getenv("THREAD_POOL_SIZE", "20"))

# 超时配置（秒）
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "120"))
VOICE_TIMEOUT = int(os.getenv("VOICE_TIMEOUT", "120"))  # 增加到 120 秒，避免长文本超时

# 飞书机器人并发配置
FEISHU_MAX_USERS = int(os.getenv("FEISHU_MAX_USERS", "50"))  # 最大并发用户数
FEISHU_USER_TIMEOUT = int(os.getenv("FEISHU_USER_TIMEOUT", "10"))  # 用户不活跃超时（秒）

# ==========================================
# Langfuse 监控配置
# ==========================================
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

# langfuse v4 需要环境变量
if LANGFUSE_PUBLIC_KEY:
    os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
if LANGFUSE_SECRET_KEY:
    os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
if LANGFUSE_HOST:
    os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST
