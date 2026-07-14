# Master Chen Divination（陈大师算命）

一个基于 LangGraph Agent 的算命机器人，支持飞书对话和语音回复。

## 项目简介

陈大师是一个 AI 算命先生，精通八字排盘、运势查询、占卜抽签、周公解梦等功能。用户可以通过飞书机器人与陈大师对话，并获得文字和语音回复。

## 项目结构

```
MasterChenDivination/
├── server.py                  # FastAPI 后端服务（核心）
├── MyAgent.py                 # LangGraph Agent 定义（情绪检测、消息压缩、工具调用）
├── MyTools.py                 # 工具集（八字排盘、RAG 知识库、占卜、解梦、TTS 语音）
├── config.py                  # 配置加载模块（从 .env 读取）
├── .env.example               # 配置模板（复制为 .env 后填写）
├── .gitignore
├── feishu_master_chen.py      # 飞书前端（WebSocket 长连接）
├── feishu_bot.py              # 飞书机器人（备用）
├── sys_logger.py              # 日志模块
├── sys_memory.py              # Redis 持久化模块
├── start_redis.ps1            # Redis 启动脚本
├── local_qdrant/              # Qdrant 向量数据库（首次运行自动创建）
├── docs/                      # 设计文档
│   ├── custom/                # 自定义文档
│   └── superpowers/           # 设计规格和实现计划
── html/                      # 参考资料
```

## 功能模块

| 模块 | 说明 |
|------|------|
| **八字排盘** | 通过缘份居 API 查询八字信息 |
| **运势查询** | 本地 RAG 知识库（Qdrant）查询 2026 年运势 |
| **占卜抽签** | 周易摇卦占卜 |
| **周公解梦** | 梦境解析 |
| **百度搜索** | 实时资讯搜索 |
| **语音合成** | Qwen3-TTS 带情绪控制的语音回复 |
| **消息压缩** | 对话历史自动摘要，控制 token 消耗 |
| **情绪检测** | 识别用户情绪并调整回复风格 |

## 环境配置

### 1. 创建配置文件

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填写你的 API 密钥
```

需要填写的密钥：

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | https://bailian.console.aliyun.com |
| `BAIDU_AI_SEARCH_API_KEY` | 百度 AI 搜索 API Key | https://qianfan.baidubce.com |
| `YUANFENJU_API_KEY` | 缘份居 API Key | https://www.yuanfenju.com |
| `LLM_API_KEY` | 阿里云 Token Plan API Key | 联系管理员获取 |
| `FEISHU_APP_ID` | 飞书应用 ID | 飞书开放平台创建应用后获取 |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | 飞书开放平台创建应用后获取 |

### 2. 安装依赖

```bash
conda create -n py310 python=3.10
conda activate py310
pip install fastapi uvicorn langchain langgraph qdrant-client \
    dashscope python-dotenv pydub lark-oapi requests beautifulsoup4
```

### 3. 启动 Redis

```bash
# Windows
powershell -ExecutionPolicy Bypass -File start_redis.ps1

# 或手动启动
redis-server.exe
```

## 使用方式

### 方式一：直接启动后端服务

```bash
python server.py
```

服务启动后访问 `http://127.0.0.1:8000`

**API 接口：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 健康检查 |
| `/chat` | POST | 对话（参数：`query`） |
| `/get_audio` | POST | 生成语音（参数：`voice_id`, `text`, `mood`） |
| `/add_urls` | POST | 添加 URL 到知识库（参数：`urls`） |

**测试示例：**

```bash
# 对话
curl -X POST "http://127.0.0.1:8000/chat?query=你好"

# 获取语音
curl -X POST "http://127.0.0.1:8000/get_audio?voice_id=test_123&text=你好世界&mood=default" -o output.wav
```

### 方式二：通过飞书机器人使用

```bash
python feishu_master_chen.py
```

飞书前端会：
1. 自动启动 server.py
2. 连接飞书 WebSocket
3. 接收消息 → 转发给 server.py → 发送文字和语音回复

## 语音情绪

| 情绪 | 说明 |
|------|------|
| `default` | 平静沉稳，像经验丰富的算命先生 |
| `upbeat` | 兴奋激动，热情有活力 |
| `angry` | 愤怒严厉，不满和警告 |
| `depressed` | 悲伤低沉，忧虑和同情 |
| `friendly` | 友好温和，亲切和关怀 |
| `cheerful` | 开心愉悦，高兴和乐观 |

## 注意事项

- **`.env` 文件包含敏感信息，不要上传到 GitHub**
- Windows 环境下需要修复 SSL 证书问题（代码已自动处理）
- 首次使用通过 `/add_urls` 接口添加 URL，会自动创建 Qdrant 知识库
- 语音合成需要网络连接（调用阿里云百炼 API）
