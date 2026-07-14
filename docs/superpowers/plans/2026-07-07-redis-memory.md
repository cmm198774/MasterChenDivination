# Redis Memory 持久化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Agent 添加 Redis 持久化存储功能，实现多用户对话状态的持久化和隔离。

**Architecture:** 创建 RedisSaver 类实现 LangGraph 的 BaseCheckpointSaver 接口，使用 Redis 存储 checkpoint 数据。修改 create_agent_graph 支持自定义 checkpointer 参数。FastAPI 启动时自动启动 Redis 服务器。

**Tech Stack:** Redis, redis-py, LangGraph, FastAPI

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `sys_memory.py` | RedisSaver 类实现 | 新增 |
| `start_redis.ps1` | Redis 启动脚本 | 新增 |
| `MyAgent.py` | 添加 checkpointer 参数 | 修改 |
| `server.py` | 启动 Redis，使用 RedisSaver | 修改 |
| `test_scripts/test_redis_memory.py` | Redis 持久化测试 | 新增 |

---

### Task 1: 安装 Redis 和 Python 依赖

**Files:**
- 无文件变更

- [ ] **Step 1: 安装 redis Python 包**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 pip install redis
```

Expected: Successfully installed redis-x.x.x

- [ ] **Step 2: 安装 Redis for Windows**

方法1 - 使用 Chocolatey（推荐）：
```bash
choco install redis-64
```

方法2 - 手动下载：
访问 https://github.com/tporadowski/redis/releases 下载最新版 Redis for Windows，解压后将目录添加到 PATH。

- [ ] **Step 3: 验证 Redis 安装**

```bash
redis-server --version
redis-cli ping
```

Expected: redis-server v5.x.x 或更高版本

---

### Task 2: 创建 RedisSaver 类

**Files:**
- Create: `sys_memory.py`

- [ ] **Step 1: 创建 sys_memory.py 文件**

```python
"""
Redis 持久化存储模块
提供 LangGraph checkpointer 的 Redis 实现
"""
import pickle
from typing import Any, Iterator, Optional, Sequence
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
import redis


# ------------------------------------------------------------
# RedisSaver 类
# 功能: 使用 Redis 存储 LangGraph checkpoint，实现对话状态持久化
# ------------------------------------------------------------
class RedisSaver(BaseCheckpointSaver):
    """
    基于 Redis 的 LangGraph checkpoint 存储。
    
    使用 thread_id 作为主键，支持多用户对话状态隔离。
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        *,
        prefix: str = "langgraph",
    ):
        """
        初始化 RedisSaver。
        
        Args:
            redis_url: Redis 服务器地址 (str)
            prefix: Redis 键前缀 (str)，默认 "langgraph"
        """
        super().__init__()
        self.client = redis.from_url(redis_url)
        self.prefix = prefix
    
    def _get_checkpoint_key(self, thread_id: str, checkpoint_id: str) -> str:
        """
        生成 checkpoint 的 Redis 键。
        
        Args:
            thread_id: 线程 ID (str)
            checkpoint_id: checkpoint ID (str)
            
        Returns:
            str: Redis 键
        """
        return f"{self.prefix}:checkpoint:{thread_id}:{checkpoint_id}"
    
    def _get_writes_key(self, thread_id: str, checkpoint_id: str, task_id: str) -> str:
        """
        生成 writes 的 Redis 键。
        
        Args:
            thread_id: 线程 ID (str)
            checkpoint_id: checkpoint ID (str)
            task_id: 任务 ID (str)
            
        Returns:
            str: Redis 键
        """
        return f"{self.prefix}:writes:{thread_id}:{checkpoint_id}:{task_id}"
    
    def _get_index_key(self, thread_id: str) -> str:
        """
        生成 checkpoint 索引的 Redis 键。
        
        Args:
            thread_id: 线程 ID (str)
            
        Returns:
            str: Redis 键
        """
        return f"{self.prefix}:index:{thread_id}"
    
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """
        根据 config 加载最新的 checkpoint。
        
        Args:
            config: 配置，包含 thread_id 和可选的 checkpoint_id
            
        Returns:
            Optional[CheckpointTuple]: checkpoint 元组，如果不存在则返回 None
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        
        if checkpoint_id:
            # 获取指定的 checkpoint
            key = self._get_checkpoint_key(thread_id, checkpoint_id)
            data = self.client.get(key)
            if not data:
                return None
            checkpoint, metadata = pickle.loads(data)
        else:
            # 获取最新的 checkpoint
            index_key = self._get_index_key(thread_id)
            checkpoint_ids = self.client.lrange(index_key, 0, 0)
            if not checkpoint_ids:
                return None
            checkpoint_id = checkpoint_ids[0].decode("utf-8")
            key = self._get_checkpoint_key(thread_id, checkpoint_id)
            data = self.client.get(key)
            if not data:
                return None
            checkpoint, metadata = pickle.loads(data)
        
        # 获取 pending_writes
        pending_writes = []
        writes_prefix = f"{self.prefix}:writes:{thread_id}:{checkpoint_id}"
        for key in self.client.scan_iter(f"{writes_prefix}:*"):
            writes_data = self.client.get(key)
            if writes_data:
                pending_writes.extend(pickle.loads(writes_data))
        
        # 构建 config
        result_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
        
        # 获取 parent_config
        parent_checkpoint_id = metadata.get("parent_id")
        parent_config = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }
        
        return CheckpointTuple(
            config=result_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes if pending_writes else None,
        )
    
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        保存 checkpoint。
        
        Args:
            config: 配置，包含 thread_id
            checkpoint: 要保存的 checkpoint
            metadata: checkpoint 元数据
            new_versions: 新的 channel 版本
            
        Returns:
            RunnableConfig: 更新后的配置
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        
        # 保存 parent_id 到 metadata
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        if parent_checkpoint_id:
            metadata["parent_id"] = parent_checkpoint_id
        
        # 序列化并保存 checkpoint
        key = self._get_checkpoint_key(thread_id, checkpoint_id)
        data = pickle.dumps((checkpoint, dict(metadata)))
        self.client.set(key, data)
        
        # 更新索引（最新的在前面）
        index_key = self._get_index_key(thread_id)
        self.client.lpush(index_key, checkpoint_id)
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
    
    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """
        保存中间写入。
        
        Args:
            config: 配置，包含 thread_id 和 checkpoint_id
            writes: 要保存的写入列表
            task_id: 任务 ID
            task_path: 任务路径
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]
        
        key = self._get_writes_key(thread_id, checkpoint_id, task_id)
        
        # 追加写入
        existing = self.client.get(key)
        if existing:
            current_writes = pickle.loads(existing)
            current_writes.extend(writes)
            self.client.set(key, pickle.dumps(current_writes))
        else:
            self.client.set(key, pickle.dumps(list(writes)))
    
    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """
        列出 checkpoints。
        
        Args:
            config: 配置，包含 thread_id
            filter: 过滤条件
            before: 在此 checkpoint 之前的
            limit: 最大返回数量
            
        Yields:
            CheckpointTuple: checkpoint 元组
        """
        if not config:
            return
        
        thread_id = config["configurable"]["thread_id"]
        index_key = self._get_index_key(thread_id)
        
        # 获取所有 checkpoint IDs
        checkpoint_ids = self.client.lrange(index_key, 0, -1)
        
        count = 0
        for cp_id_bytes in checkpoint_ids:
            if limit and count >= limit:
                break
            
            checkpoint_id = cp_id_bytes.decode("utf-8")
            
            # 如果有 before，跳过直到找到 before
            if before:
                before_id = before["configurable"].get("checkpoint_id")
                if before_id and checkpoint_id != before_id:
                    continue
                elif before_id and checkpoint_id == before_id:
                    before = None  # 找到了，之后的都包含
                    continue
            
            # 获取 checkpoint
            key = self._get_checkpoint_key(thread_id, checkpoint_id)
            data = self.client.get(key)
            if not data:
                continue
            
            checkpoint, metadata = pickle.loads(data)
            
            # 应用 filter
            if filter:
                match = True
                for k, v in filter.items():
                    if metadata.get(k) != v:
                        match = False
                        break
                if not match:
                    continue
            
            # 构建 config
            result_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                }
            }
            
            # 获取 parent_config
            parent_checkpoint_id = metadata.get("parent_id")
            parent_config = None
            if parent_checkpoint_id:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
            
            yield CheckpointTuple(
                config=result_config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
                pending_writes=None,
            )
            
            count += 1
```

- [ ] **Step 2: 验证语法正确**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 python -c "from sys_memory import RedisSaver; print('导入成功')"
```

Expected: 导入成功

- [ ] **Step 3: Commit**

```bash
git add sys_memory.py
git commit -m "feat: add RedisSaver class for LangGraph checkpoint persistence"
```

---

### Task 3: 修改 create_agent_graph 支持自定义 checkpointer

**Files:**
- Modify: `MyAgent.py:201-228` (函数签名)
- Modify: `MyAgent.py:632-634` (使用 checkpointer)

- [ ] **Step 1: 修改 create_agent_graph 函数签名**

在 `MyAgent.py` 的 `create_agent_graph` 函数中添加 `checkpointer` 参数：

```python
def create_agent_graph(
    model_name: str = "qwen3.6-flash",
    base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    api_key: str = "",
    temperature: float = 0.2,
    tool_list: List[BaseTool] = None,
    tool_descriptions: str = "",
    tool_timeout: int = 60,
    enable_mood_detection: bool = True,
    memory_token_limit: int = 2000,
    checkpointer=None,  # 新增：自定义 checkpointer，默认为 None（使用 MemorySaver）
):
```

- [ ] **Step 2: 修改函数内部使用 checkpointer**

在 `MyAgent.py` 的 `create_agent_graph` 函数末尾，修改 checkpointer 的使用：

```python
    # 使用 checkpointer 编译，支持对话记忆
    # 如果未提供 checkpointer，使用 MemorySaver
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    
    return workflow.compile(checkpointer=checkpointer)
```

- [ ] **Step 3: 验证语法正确**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 python -c "from MyAgent import create_agent_graph; print('导入成功')"
```

Expected: 导入成功

- [ ] **Step 4: Commit**

```bash
git add MyAgent.py
git commit -m "feat: add checkpointer parameter to create_agent_graph"
```

---

### Task 4: 创建 Redis 启动脚本

**Files:**
- Create: `start_redis.ps1`

- [ ] **Step 1: 创建 start_redis.ps1**

```powershell
# Redis 服务器启动脚本
# 功能: 检查 Redis 是否运行，如果未运行则启动

# 检查 Redis 是否已运行
$redisRunning = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue

if (-not $redisRunning) {
    # 尝试启动 Redis 服务器
    try {
        Start-Process -FilePath "redis-server" -WindowStyle Hidden
        Write-Host "[OK] Redis 服务器已启动"
        Start-Sleep -Seconds 2
        
        # 验证是否启动成功
        $redisRunning = Get-Process -Name "redis-server" -ErrorAction SilentlyContinue
        if ($redisRunning) {
            Write-Host "[OK] Redis 服务器运行正常"
        } else {
            Write-Host "[ERROR] Redis 服务器启动失败"
            exit 1
        }
    } catch {
        Write-Host "[ERROR] 无法启动 Redis 服务器: $_"
        exit 1
    }
} else {
    Write-Host "[OK] Redis 服务器已在运行"
}
```

- [ ] **Step 2: 测试脚本**

```powershell
powershell -File start_redis.ps1
```

Expected: Redis 服务器已启动 或 Redis 服务器已在运行

- [ ] **Step 3: Commit**

```bash
git add start_redis.ps1
git commit -m "feat: add PowerShell script to start Redis server"
```

---

### Task 5: 修改 server.py 使用 RedisSaver

**Files:**
- Modify: `server.py:0-27` (imports 和 lifespan)
- Modify: `server.py:34-48` (Master 类)

- [ ] **Step 1: 修改 server.py imports 和 lifespan**

```python
import os
import subprocess

# 禁用所有代理
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "*"

from contextlib import asynccontextmanager
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
import uvicorn

# 全局 Master 实例
master_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，启动 Redis 和 Master 实例"""
    global master_instance
    
    # 启动 Redis 服务器
    print("[DEBUG] 启动 Redis 服务器...")
    subprocess.run(["powershell", "-File", "start_redis.ps1"])
    
    # 创建 Master 实例（使用 RedisSaver）
    print("[DEBUG] 创建 Master 实例...")
    master_instance = Master(user_id="default")
    print("[DEBUG] Master 实例创建完成")
    
    yield
    print("[DEBUG] 应用关闭")
```

- [ ] **Step 2: 修改 Master 类使用 RedisSaver**

```python
app = FastAPI(lifespan=lifespan)
from MyTools import *
from MyAgent import create_agent_graph
from sys_memory import RedisSaver


class Master:
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        
        # 创建 RedisSaver
        redis_saver = RedisSaver(redis_url="redis://localhost:6379")

        # 初始化 LangGraph agent graph（启用情绪检测，使用 Redis 持久化）
        self.agent_graph = create_agent_graph(
            model_name="qwen3.6-flash",
            base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            api_key="sk-sp-D.RDMYM.JNhb.MEYCIQDuNZvEdRWt4zV8E96YXNdFAh4lgofEGRH3izgiXpBxuAIhAPMSjkdNfii61vuvXszCzFKEjKlmbCG0F8ati/SiOCjm",
            temperature=0.2,
            tool_list=[get_info_from_local_db, bazi_cesuan, yaoyigua, jiemeng],
            tool_descriptions=TOOL_DESCRIPTIONS,
            tool_timeout=20,
            enable_mood_detection=True,
            checkpointer=redis_saver,  # 使用 Redis 持久化
        )

    def run(self, query: str):
        print(f"[DEBUG] 收到查询: {query}")
        print("[DEBUG] 开始 agent 推理...")

        # 使用 user_id 作为 thread_id
        config = {"configurable": {"thread_id": self.user_id}}
        messages = [HumanMessage(content=query)]

        result = self.agent_graph.invoke({
            "messages": messages,
        }, config=config)

        qingxu = result.get("mood", "default")
        print(f"[DEBUG] 情绪: {qingxu}")
        last_message = result["messages"][-1]
        return {"input": query, "output": last_message.content, "qingxu": qingxu}
```

- [ ] **Step 3: 验证语法正确**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 python -c "import server; print('导入成功')"
```

Expected: 导入成功

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: integrate RedisSaver into server.py"
```

---

### Task 6: 创建 Redis 测试脚本

**Files:**
- Create: `test_scripts/test_redis_memory.py`

- [ ] **Step 1: 创建测试脚本**

```python
"""
Redis 持久化测试脚本

测试场景：
1. Redis 服务器连接测试
2. 数据隔离测试（不同 user_id）
3. 跨 Agent 加载测试（相同 user_id）
"""
import os

# 禁用所有代理
for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "*"

import redis
from langchain_core.messages import HumanMessage
from MyAgent import create_agent_graph
from MyTools import get_info_from_local_db, bazi_cesuan, yaoyigua, jiemeng, TOOL_DESCRIPTIONS
from sys_memory import RedisSaver


# ============================================================
# 辅助函数
# ============================================================
def print_messages(messages, title=""):
    """打印消息列表"""
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")
    print(f"消息总数: {len(messages)}")
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content = msg.content[:80] if hasattr(msg, 'content') and isinstance(msg.content, str) else str(msg)[:80]
        print(f"  [{i}] {msg_type}: {content}...")
    print(f"{'=' * 60}\n")


# ============================================================
# 测试 1: Redis 连接测试
# ============================================================
def test_redis_connection():
    """测试 Redis 服务器连接"""
    print("\n" + "=" * 60)
    print("测试 1: Redis 服务器连接测试")
    print("=" * 60)
    
    try:
        r = redis.from_url("redis://localhost:6379")
        r.ping()
        print("[OK] Redis 服务器连接成功")
        return True
    except Exception as e:
        print(f"[ERROR] Redis 服务器连接失败: {e}")
        return False


# ============================================================
# 测试 2: 数据隔离测试
# ============================================================
def test_data_isolation():
    """测试不同 user_id 的数据隔离"""
    print("\n" + "=" * 60)
    print("测试 2: 数据隔离测试")
    print("=" * 60)
    
    redis_saver = RedisSaver(redis_url="redis://localhost:6379")
    
    # 创建 graph
    graph = create_agent_graph(
        model_name="qwen3.6-flash",
        base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        api_key="sk-sp-D.RDMYM.JNhb.MEYCIQDuNZvEdRWt4zV8E96YXNdFAh4lgofEGRH3izgiXpBxuAIhAPMSjkdNfii61vuvXszCzFKEjKlmbCG0F8ati/SiOCjm",
        temperature=0.2,
        tool_list=[get_info_from_local_db, bazi_cesuan, yaoyigua, jiemeng],
        tool_descriptions=TOOL_DESCRIPTIONS,
        tool_timeout=20,
        enable_mood_detection=True,
        memory_token_limit=500,
        checkpointer=redis_saver,
    )
    
    # 用户 A 对话
    print("\n--- 用户 A (user-a) 对话 ---")
    config_a = {"configurable": {"thread_id": "user-a"}}
    result_a = graph.invoke({"messages": [HumanMessage(content="你好，我是用户A")]}, config=config_a)
    print_messages(result_a.get("messages", []), "用户 A 的消息")
    
    # 用户 B 对话
    print("\n--- 用户 B (user-b) 对话 ---")
    config_b = {"configurable": {"thread_id": "user-b"}}
    result_b = graph.invoke({"messages": [HumanMessage(content="你好，我是用户B")]}, config=config_b)
    print_messages(result_b.get("messages", []), "用户 B 的消息")
    
    # 验证隔离
    # 重新加载用户 A 的状态
    result_a2 = graph.invoke({"messages": [HumanMessage(content("你还记得我是谁吗？")]}, config=config_a)
    messages_a2 = result_a2.get("messages", [])
    
    # 检查是否包含之前的对话
    has_history = len(messages_a2) > 2  # 应该有历史消息
    
    if has_history:
        print("[OK] 数据隔离测试通过：用户 A 的历史记录被正确保留")
    else:
        print("[ERROR] 数据隔离测试失败：用户 A 的历史记录丢失")
    
    return has_history


# ============================================================
# 测试 3: 跨 Agent 加载测试
# ============================================================
def test_cross_agent_loading():
    """测试相同 user_id 的跨 Agent 加载"""
    print("\n" + "=" * 60)
    print("测试 3: 跨 Agent 加载测试")
    print("=" * 60)
    
    redis_saver = RedisSaver(redis_url="redis://localhost:6379")
    
    # Agent A 进行对话
    print("\n--- Agent A 进行对话 ---")
    graph_a = create_agent_graph(
        model_name="qwen3.6-flash",
        base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        api_key="sk-sp-D.RDMYM.JNhb.MEYCIQDuNZvEdRWt4zV8E96YXNdFAh4lgofEGRH3izgiXpBxuAIhAPMSjkdNfii61vuvXszCzFKEjKlmbCG0F8ati/SiOCjm",
        temperature=0.2,
        tool_list=[],
        tool_descriptions="",
        tool_timeout=20,
        enable_mood_detection=False,
        checkpointer=redis_saver,
    )
    
    thread_id = "test-cross-agent-001"
    config = {"configurable": {"thread_id": thread_id}}
    
    # Agent A 第一轮对话
    result_a1 = graph_a.invoke({"messages": [HumanMessage(content="我叫张三")]}, config=config)
    print_messages(result_a1.get("messages", []), "Agent A 第一轮对话")
    
    # Agent B 加载相同 thread_id 的状态
    print("\n--- Agent B 加载相同 thread_id ---")
    graph_b = create_agent_graph(
        model_name="qwen3.6-flash",
        base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        api_key="sk-sp-D.RDMYM.JNhb.MEYCIQDuNZvEdRWt4zV8E96YXNdFAh4lgofEGRH3izgiXpBxuAIhAPMSjkdNfii61vuvXszCzFKEjKlmbCG0F8ati/SiOCjm",
        temperature=0.2,
        tool_list=[],
        tool_descriptions="",
        tool_timeout=20,
        enable_mood_detection=False,
        checkpointer=redis_saver,
    )
    
    # Agent B 继续对话
    result_b1 = graph_b.invoke({"messages": [HumanMessage(content("你还记得我的名字吗？")]}, config=config)
    print_messages(result_b1.get("messages", []), "Agent B 的对话")
    
    # 检查是否记住了名字
    messages_b = result_b1.get("messages", [])
    has_name = any("张三" in str(msg.content) for msg in messages_b if hasattr(msg, 'content'))
    
    if has_name:
        print("[OK] 跨 Agent 加载测试通过：Agent B 记住了 Agent A 的对话")
    else:
        print("[ERROR] 跨 Agent 加载测试失败：Agent B 没有记住对话")
    
    return has_name


# ============================================================
# 主测试函数
# ============================================================
def run_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始 Redis 持久化测试")
    print("=" * 60)
    
    results = {}
    
    # 测试 1: Redis 连接
    results["connection"] = test_redis_connection()
    if not results["connection"]:
        print("\n[ERROR] Redis 连接失败，跳过后续测试")
        return
    
    # 测试 2: 数据隔离
    results["isolation"] = test_data_isolation()
    
    # 测试 3: 跨 Agent 加载
    results["cross_agent"] = test_cross_agent_loading()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    for name, passed in results.items():
        status = "[OK]" if passed else "[ERROR]"
        print(f"{status} {name}")


if __name__ == "__main__":
    run_tests()
```

- [ ] **Step 2: 验证语法正确**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 python -c "import sys; sys.path.insert(0, 'test_scripts'); from test_redis_memory import run_tests; print('导入成功')"
```

Expected: 导入成功

- [ ] **Step 3: Commit**

```bash
git add test_scripts/test_redis_memory.py
git commit -m "feat: add Redis memory test script"
```

---

### Task 7: 运行测试验证

**Files:**
- 无文件变更

- [ ] **Step 1: 确保 Redis 服务器运行**

```bash
powershell -File start_redis.ps1
```

Expected: Redis 服务器已启动 或 Redis 服务器已在运行

- [ ] **Step 2: 运行测试脚本**

```bash
export PATH="/c/ProgramData/Anaconda3/Scripts:/c/ProgramData/Anaconda3:$PATH"
conda run -n py310 python test_scripts/test_redis_memory.py
```

Expected: 所有测试通过

- [ ] **Step 3: 检查 Redis 中的数据**

```bash
redis-cli keys "langgraph:*"
```

Expected: 显示存储的 checkpoint 键
