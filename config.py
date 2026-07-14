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
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
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
QDRANT_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_qdrand")

# Redis 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# 超时配置（秒）
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "120"))
VOICE_TIMEOUT = int(os.getenv("VOICE_TIMEOUT", "60"))
