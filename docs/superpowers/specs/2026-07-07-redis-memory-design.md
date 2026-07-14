# Redis Memory 持久化设计文档

## 概述

为 Agent 添加 Redis 持久化存储功能，替代 MemorySaver，实现多用户对话状态的持久化存储和隔离。

## 目标

1. 使用 Redis 作为数据存储，持久化 AgentState
2. 使用 user_id 作为主键，实现不同用户对话状态隔离
3. 提供 checkpointer 接口，与 LangGraph 原生集成
4. FastAPI 启动时自动启动 Redis 服务器

## 架构设计

### 1. sys_memory.py 模块

#### RedisSaver 类

实现 LangGraph 的 `BaseCheckpointSaver` 接口：

```python
class RedisSaver(BaseCheckpointSaver):
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """初始化 Redis 连接"""
        
    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """根据 config 加载状态"""
        
    def put(self, config: dict, checkpoint: Checkpoint, metadata: dict) -> None:
        """保存状态"""
        
    def list(self, config: Optional[dict]) -> Iterator[CheckpointTuple]:
        """列出所有状态"""
```

#### 数据结构

Redis 键设计：
- `agent_state:{user_id}` - 存储完整的 AgentState

序列化方式：
- 使用 `pickle` 序列化 AgentState（包括 BaseMessage 对象）
- 或使用 `json` + 自定义序列化器（更安全，但需要更多代码）

**推荐：使用 pickle**，因为 BaseMessage 对象较复杂。

### 2. 修改 create_agent_graph

添加 `checkpointer` 参数：

```python
def create_agent_graph(
    model_name: str = "qwen3.6-flash",
    # ... 其他参数
    checkpointer: BaseCheckpointSaver = None,  # 新增参数
):
    # 如果未提供 checkpointer，使用 MemorySaver
    if checkpointer is None:
        checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer)
```

### 3. Redis 安装与启动

#### 安装 Redis for Windows

使用 Chocolatey 或手动下载：
```bash
choco install redis-64
```

或从 GitHub 下载：https://github.com/tporadowski/redis/releases

#### PowerShell 启动脚本

创建 `start_redis.ps1`：

```powershell
# 检查 Redis 是否已运行
$redisRunning = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue

if (-not $redisRunning) {
    # 启动 Redis 服务器
    Start-Process -FilePath "redis-server" -WindowStyle Hidden
    Write-Host "Redis 服务器已启动"
    Start-Sleep -Seconds 2
} else {
    Write-Host "Redis 服务器已在运行"
}
```

#### 修改 FastAPI lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动 Redis 服务器
    subprocess.run(["powershell", "-File", "start_redis.ps1"])
    
    # 创建 Master 实例
    global master_instance
    master_instance = Master(user_id="default")
    
    yield
    # 清理
```

## 使用示例

### 使用 MemorySaver（默认）

```python
graph = create_agent_graph(
    model_name="qwen3.6-flash",
    # 不传 checkpointer，默认使用 MemorySaver
)
```

### 使用 RedisSaver

```python
from sys_memory import RedisSaver

redis_saver = RedisSaver(redis_url="redis://localhost:6379")
graph = create_agent_graph(
    model_name="qwen3.6-flash",
    checkpointer=redis_saver,
)

# 使用 config 指定 user_id
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": [HumanMessage(content="你好")]}, config=config)
```

## 测试计划

### 1. Redis 服务器测试

- 检查 Redis 服务器是否正常启动
- 检查是否可以连接到 Redis

### 2. 数据隔离测试

- 使用不同的 user_id 进行对话
- 验证不同 user_id 的状态是否隔离

### 3. 跨 Agent 加载测试

- 修改 test_agent.py
- Agent A 使用 user_id="test-001" 进行对话
- Agent B 使用相同的 user_id="test-001" 加载状态
- 验证 Agent B 是否能正确恢复对话历史

### 4. server.py 测试

- 启动 FastAPI 时检查 Redis 是否自动启动
- 通过 API 进行对话测试

## 依赖

需要安装：
- `redis` Python 包：`pip install redis`
- Redis for Windows（通过 Chocolatey 或手动安装）

## 文件清单

新增文件：
- `sys_memory.py` - Redis checkpointer 实现
- `start_redis.ps1` - Redis 启动脚本

修改文件：
- `MyAgent.py` - 添加 checkpointer 参数
- `server.py` - 修改 lifespan，启动 Redis
- `test_scripts/test_agent.py` - 添加 Redis 测试用例
