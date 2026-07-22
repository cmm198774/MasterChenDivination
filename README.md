# Master Chen Divination（陈大师算命）

一个基于 LangGraph Agent 的算命机器人，支持多用户并发、飞书对话和语音回复。

## 项目简介

陈大师是一个 AI 算命先生，精通八字排盘、运势查询、占卜抽签、周公解梦等功能。系统支持多用户并发访问，每个用户拥有独立的对话历史和上下文。用户可以通过飞书机器人与陈大师对话，并获得文字和语音回复。

### 核心特性

- **多用户并发支持**：服务器使用线程池处理并发请求，支持多个用户同时对话
- **飞书多用户并行**：每个用户独立队列，保证消息顺序的同时实现并行处理
- **对话历史隔离**：基于 Redis 的用户状态管理，不同用户的对话互不干扰
- **自动资源清理**：不活跃用户自动释放资源，防止内存泄漏
- **Redis 自动管理**：服务启动时自动启动 Redis，关闭时自动停止
- **LLM 调用监控**：集成 Langfuse，自动记录模型调用链路、Token 用量和耗时

## 项目结构

```
MasterChenDivination/
├── server.py                  # FastAPI 后端服务（支持并发，线程池处理）
├── MyAgent.py                 # LangGraph Agent 定义（情绪检测、消息压缩、工具调用）
├── MyTools.py                 # 工具集（八字排盘、RAG 知识库、占卜、解梦、TTS 语音）
├── config.py                  # 配置加载模块（从 .env 读取）
├── .env.example               # 配置模板（复制为 .env 后填写）
├── .gitignore
├── feishu_master_chen.py      # 飞书前端（多用户并行处理，线程池架构）
├── feishu_bot.py              # 飞书机器人（备用）
├── sys_logger.py              # 日志模块
├── sys_memory.py              # Redis 持久化模块（支持多用户隔离）
├── start_redis.py             # Redis 自动管理模块（启动/停止）
├── langfuse/                  # Langfuse 监控（Docker 部署）
│   ├── docker-compose.yml     # Docker 编排文件
│   └── .env                   # Langfuse 环境变量
├── local_qdrant/              # Qdrant 向量数据库（首次运行自动创建）
├── redis_cache/               # Redis 数据目录
├── logs/                      # 日志目录（自动创建）
├── docs/                      # 设计文档
│   ├── custom/                # 自定义文档
│   └── superpowers/           # 设计规格和实现计划
└── html/                      # 参考资料
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

可选配置（并发相关）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `THREAD_POOL_SIZE` | 20 | 服务器线程池大小 |
| `FEISHU_MAX_USERS` | 50 | 飞书最大并发用户数 |
| `FEISHU_USER_TIMEOUT` | 300 | 用户不活跃超时时间（秒） |
| `CHAT_TIMEOUT` | 120 | 对话请求超时时间（秒） |
| `VOICE_TIMEOUT` | 120 | 语音生成超时时间（秒） |

Langfuse 监控配置（可选）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LANGFUSE_PUBLIC_KEY` | 空 | Langfuse 公钥（从 Web 界面获取） |
| `LANGFUSE_SECRET_KEY` | 空 | Langfuse 私钥（从 Web 界面获取） |
| `LANGFUSE_HOST` | http://localhost:3000 | Langfuse 服务地址 |

### 2. 安装依赖

```bash
conda create -n py310 python=3.10
conda activate py310
pip install fastapi uvicorn langchain langgraph qdrant-client \
    dashscope python-dotenv pydub lark-oapi requests beautifulsoup4 langfuse
```

### 3. 启动 Redis

Redis 会在服务启动时自动启动，无需手动操作。

如需手动管理：
```bash
# 自动启动（推荐）
python server.py  # Redis 会自动启动

# 手动启动
python -c "from start_redis import start_redis_server; start_redis_server()"

# 手动停止
python -c "from start_redis import stop_redis_server; stop_redis_server()"
```

### 4. Langfuse 监控（可选）

用于监控 LLM 调用链路、Token 用量和耗时分析。

```bash
# 1. 确保 Docker Desktop 已启动

# 2. 启动 Langfuse
cd langfuse
docker compose up -d

# 3. 打开浏览器访问 http://localhost:3000
#    注册账号 → 创建项目 → 获取 API Keys

# 4. 将密钥填入项目根目录的 .env 文件：
#    LANGFUSE_PUBLIC_KEY=pk-...
#    LANGFUSE_SECRET_KEY=sk-...
#    LANGFUSE_HOST=http://localhost:3000

# 5. 启动服务即可自动上报监控数据
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
| `/chat` | POST | 对话（参数：`query`, `user_id`） |
| `/get_audio` | POST | 生成语音（参数：`voice_id`, `text`, `mood`） |
| `/add_urls` | POST | 添加 URL 到知识库（参数：`urls`） |

**测试示例：**

```bash
# 对话（指定用户 ID，支持多用户并发）
curl -X POST "http://127.0.0.1:8000/chat?query=你好&user_id=user_001"

# 获取语音
curl -X POST "http://127.0.0.1:8000/get_audio?voice_id=test_123&text=你好世界&mood=default" -o output.wav
```

**多用户支持：**
- 每个 `user_id` 拥有独立的对话历史
- 服务器使用线程池（默认 20 个线程）处理并发请求
- 不同用户的请求互不干扰，可同时处理

### 方式二：通过飞书机器人使用

```bash
python feishu_master_chen.py
```

飞书前端会：
1. 自动启动 server.py
2. 连接飞书 WebSocket
3. 接收消息 → 转发给 server.py → 发送文字和语音回复

**飞书多用户并行处理：**
- 每个用户拥有独立的消息队列和 Worker 线程
- 同一用户的消息按顺序处理（保证对话上下文）
- 不同用户的消息并行处理（提高并发能力）
- 用户不活跃后自动清理（默认 5 分钟）
- 最大并发用户数可配置（默认 50）

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

## 技术架构

### 并发处理架构

```
┌─────────────────────────────────────────┐
│         ThreadPoolExecutor              │
│         (固定 20 个线程)                 │
├─────────────────────────────────────────┤
│  Thread 1  │  Thread 2  │  Thread 3     │
│            │            │    ...        │
│  Thread 18 │  Thread 19 │  Thread 20    │
└─────────────────────────────────────────┘
         │           │           │
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ 用户A队列 │ │ 用户B队列 │ │ 用户C队列 │
    └─────────┘ └─────────┘ └─────────┘
```

**特点：**
- 每个用户拥有独立的消息队列
- 线程池控制并发数（默认 20 个线程）
- 同一用户的消息按顺序处理（保持对话上下文）
- 不同用户的消息并行处理（提高吞吐量）
- 用户不活跃后自动清理（默认 5 分钟）

### 多用户隔离

- **对话历史隔离**：基于 Redis 的 `thread_id` 机制，每个用户的对话历史独立存储
- **日志标识**：所有日志都包含 `[{user_id}]` 前缀，方便调试和追踪
- **资源管理**：自动清理不活跃用户，防止内存泄漏

## Docker 部署（推荐）

使用 Docker 完全隔离部署，本地开发环境不受影响。

### 优势

- ✅ **完全隔离** - 容器独立运行，不映射文件到本地
- ✅ **一键启动** - `docker compose up` 启动所有服务
- ✅ **自动适配** - 代码自动检测 Docker 环境，选择正确配置
- ✅ **数据持久化** - 使用 Docker named volumes，数据安全
- ✅ **端口隔离** - 内部服务（Redis/Qdrant）不映射，避免冲突

### 快速启动

```bash
# 1. 确保 Docker Desktop 已启动

# 2. 配置环境变量
cp .env.example .env  # 复制模板
# 编辑 .env，填写 API 密钥（不要修改 SERVER_HOST/REDIS_HOST 等，代码会自动选择）

# 3. 构建并启动
docker compose up -d

# 4. 查看日志
docker compose logs -f app

# 5. 停止服务
docker compose down
```

### 服务架构

```
┌─────────────────────────────────────────┐
│           Docker Network                │
│                                         │
│  ┌──────────────┐    ┌──────────────┐  │
│  │  app:8000    │───▶│ redis:6379   │  │
│  │  (主应用)     │    │ (内部访问)    │  │
│  └──────────────┘    └──────────────┘  │
│         │                               │
│         ├──▶ qdrant:6333 (内部访问)     │
│         │                               │
└─────────┼───────────────────────────────┘
          │ 端口映射 8000:8000
          ▼
    宿主机 localhost:8000
```

### 服务端口

| 服务 | 容器端口 | 宿主机映射 | 说明 |
|------|----------|------------|------|
| App | 8000 | 8000 | 主应用（飞书 WebSocket 出站） |
| Redis | 6379 | ❌ 不映射 | 容器内访问（`redis://redis:6379`） |
| Qdrant | 6333 |  不映射 | 容器内访问（`http://qdrant:6333`） |

### 数据持久化

使用 Docker named volumes，数据存储在 Docker 管理的卷中：

| Volume | 用途 | 查看命令 |
|--------|------|----------|
| `redis_data` | Redis 数据 | `docker volume inspect redis_data` |
| `qdrant_data` | Qdrant 向量库 | `docker volume inspect qdrant_data` |

**优势：** 本地看不到这些文件，避免版本冲突和数据损坏。

### 环境变量配置

`.env` 文件只需填写密钥和端口，**不要填写主机名**（代码会自动检测）：

```env
# ✅ 需要填写
DASHSCOPE_API_KEY=sk-xxx
LLM_API_KEY=sk-yyy
FEISHU_APP_ID=cli_xxx
SERVER_PORT=8000

# ❌ 不要填写（让代码自动选择）
# SERVER_HOST=127.0.0.1
# REDIS_URL=redis://localhost:6379
```

**自动检测逻辑：**
```python
# Docker 环境
SERVER_HOST = "0.0.0.0"  # 接受外部请求
REDIS_HOST = "redis"     # Docker 网络名

# 本地环境
SERVER_HOST = "127.0.0.1"  # 只接受本地请求
REDIS_HOST = "localhost"   # 本地回环
```

### 常用命令

```bash
# 启动
docker compose up -d

# 查看日志
docker logs -f master-chen-app
docker logs --tail 100 master-chen-app

# 进入容器
docker exec -it master-chen-app bash

# 检查环境变量
docker exec master-chen-app env | grep SERVER

# 强制重建（代码更新后）
docker compose up --build -d

# 完全清理（删除数据卷）
docker compose down -v

# 查看端口映射
docker port master-chen-app

# 查看容器状态
docker ps
```

### 启用 Langfuse 监控

编辑 `docker-compose.yml`，取消 Langfuse 相关服务的注释：

```yaml
  langfuse-web:
    extends:
      file: ./langfuse/docker-compose.yml
      service: langfuse-web
  langfuse-worker:
    extends:
      file: ./langfuse/docker-compose.yml
      service: langfuse-worker
  # ... 其他 Langfuse 服务
```

然后重启：
```bash
docker compose down
docker compose up -d
```

访问 `http://localhost:3000` 注册账号并获取 API Keys，填入 `.env`。

### 本地开发 vs Docker 部署

| 场景 | 运行方式 | 数据库 | Redis |
|------|----------|--------|-------|
| 本地开发 | `python feishu_master_chen.py` | 本地 Qdrant（`./local_qdrant`） | 本地 Redis（`localhost:6379`） |
| Docker 部署 | `docker compose up -d` | 容器内 Qdrant（named volume） | 容器内 Redis（named volume） |

**完全隔离：** 本地和 Docker 可以同时运行，互不干扰。

### 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 容器启动失败 | 缺少依赖 | `docker compose build --no-cache` |
| localhost 访问不了 | SERVER_HOST 配置错误 | 删除 `.env` 中的 `SERVER_HOST` |
| 端口冲突 | 本地 Redis 占用 6379 | Docker Redis 不映射端口，无冲突 |
| 数据版本冲突 | 共享了数据目录 | 使用 named volumes，不映射本地 |
| 代码不更新 | 用了缓存镜像 | `docker compose build --no-cache` |

### 注意事项

- **`.env` 文件包含敏感信息，不要上传到 GitHub**（已加入 `.gitignore`）
- Docker 容器内使用 `redis://redis:6379` 和 `http://qdrant:6333` 访问内部服务
- 飞书 WebSocket 是出站连接，不需要额外配置端口
- 日志输出到标准输出，用 `docker logs` 查看
