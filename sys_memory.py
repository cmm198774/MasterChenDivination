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
from sys_logger import setup_global_logger

# 模块级 logger
logger = setup_global_logger()


# ------------------------------------------------------------
# RedisSaver 类
# 功能: 使用 Redis 存储 LangGraph checkpoint，实现对话状态持久化
# ------------------------------------------------------------
class RedisSaver(BaseCheckpointSaver):
    """
    基于 Redis 的 LangGraph checkpoint 存储。

    使用 thread_id 作为主键，支持多用户对话状态隔离。
    支持自动清理旧 checkpoints，防止数据无限增长。
    """

    # ------------------------------------------------------------
    # __init__
    # 功能: 初始化 Redis 连接和配置参数
    # ------------------------------------------------------------
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        *,
        prefix: str = "langgraph",
        max_checkpoints: int = 5,
    ):
        """
        初始化 RedisSaver。

        Args:
            redis_url: Redis 服务器地址 (str)
            prefix: Redis 键前缀 (str)，默认 "langgraph"
            max_checkpoints: 每个 thread 最多保留的 checkpoint 数量 (int)，默认 5
        """
        super().__init__()
        # 使用 RESP2 协议（兼容 Redis 5.0）
        self.client = redis.from_url(redis_url, protocol=2)
        self.prefix = prefix
        self.max_checkpoints = max_checkpoints

    # ------------------------------------------------------------
    # _get_checkpoint_key
    # 功能: 生成 checkpoint 数据在 Redis 中的键名
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # _get_writes_key
    # 功能: 生成中间写入数据在 Redis 中的键名
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # _get_index_key
    # 功能: 生成 checkpoint 索引列表在 Redis 中的键名（用于按时间排序）
    # ------------------------------------------------------------
    def _get_index_key(self, thread_id: str) -> str:
        """
        生成 checkpoint 索引的 Redis 键。

        Args:
            thread_id: 线程 ID (str)

        Returns:
            str: Redis 键
        """
        return f"{self.prefix}:index:{thread_id}"

    # ------------------------------------------------------------
    # _cleanup_old_checkpoints
    # 功能: 清理旧的 checkpoints，只保留最近的 max_checkpoints 个
    # ------------------------------------------------------------
    def _cleanup_old_checkpoints(self, thread_id: str) -> None:
        """
        清理旧的 checkpoints，只保留最近的 max_checkpoints 个。

        Args:
            thread_id: 线程 ID (str)
        """
        index_key = self._get_index_key(thread_id)

        # 获取所有 checkpoint IDs
        all_ids = self.client.lrange(index_key, 0, -1)

        if len(all_ids) <= self.max_checkpoints:
            return

        # 需要删除的旧 checkpoints（保留前 max_checkpoints 个）
        old_ids = all_ids[self.max_checkpoints:]

        logger.debug(f"清理旧 checkpoints: 保留 {self.max_checkpoints} 个，删除 {len(old_ids)} 个")

        for cp_id_bytes in old_ids:
            checkpoint_id = cp_id_bytes.decode("utf-8")

            # 删除 checkpoint 数据
            cp_key = self._get_checkpoint_key(thread_id, checkpoint_id)
            self.client.delete(cp_key)

            # 删除相关的 writes
            writes_prefix = f"{self.prefix}:writes:{thread_id}:{checkpoint_id}"
            for writes_key in self.client.scan_iter(f"{writes_prefix}:*"):
                self.client.delete(writes_key)

        # 修剪索引列表，只保留前 max_checkpoints 个
        self.client.ltrim(index_key, 0, self.max_checkpoints - 1)

    # ------------------------------------------------------------
    # get_tuple
    # 功能: 根据 config 从 Redis 加载 checkpoint，支持加载指定 checkpoint 或最新的
    # ------------------------------------------------------------
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """
        根据 config 加载最新的 checkpoint。

        Args:
            config: 配置，包含 thread_id 和可选的 checkpoint_id (RunnableConfig)

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
                loaded_writes = pickle.loads(writes_data)
                # 兼容旧格式（2-tuple）和新格式（3-tuple）
                for write in loaded_writes:
                    if len(write) == 2:
                        # 旧格式: (channel, value)，需要提取 task_id 从 key
                        # key 格式: prefix:writes:thread_id:checkpoint_id:task_id
                        task_id = key.decode("utf-8").split(":")[-1]
                        channel, value = write
                        pending_writes.append((task_id, channel, value))
                    else:
                        # 新格式: (task_id, channel, value)
                        pending_writes.append(write)

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

    # ------------------------------------------------------------
    # put
    # 功能: 将 checkpoint 序列化后保存到 Redis，并更新索引列表，自动清理旧数据
    # ------------------------------------------------------------
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
            config: 配置，包含 thread_id (RunnableConfig)
            checkpoint: 要保存的 checkpoint (Checkpoint)
            metadata: checkpoint 元数据 (CheckpointMetadata)
            new_versions: 新的 channel 版本 (ChannelVersions)

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

        # 清理旧的 checkpoints
        self._cleanup_old_checkpoints(thread_id)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    # ------------------------------------------------------------
    # put_writes
    # 功能: 保存中间写入数据（工具调用结果等），支持追加
    # ------------------------------------------------------------
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
            config: 配置，包含 thread_id 和 checkpoint_id (RunnableConfig)
            writes: 要保存的写入列表 (Sequence[tuple[str, Any]])
            task_id: 任务 ID (str)
            task_path: 任务路径 (str)
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]

        key = self._get_writes_key(thread_id, checkpoint_id, task_id)

        # 将 writes 转换为 3-tuple 格式: (task_id, channel, value)
        writes_with_task_id = [(task_id, channel, value) for channel, value in writes]

        # 追加写入
        existing = self.client.get(key)
        if existing:
            current_writes = pickle.loads(existing)
            current_writes.extend(writes_with_task_id)
            self.client.set(key, pickle.dumps(current_writes))
        else:
            self.client.set(key, pickle.dumps(writes_with_task_id))

    # ------------------------------------------------------------
    # list
    # 功能: 列出指定 thread 的所有 checkpoints，支持过滤、分页和排序
    # ------------------------------------------------------------
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
            config: 配置，包含 thread_id (Optional[RunnableConfig])
            filter: 过滤条件 (Optional[dict[str, Any]])
            before: 在此 checkpoint 之前的 (Optional[RunnableConfig])
            limit: 最大返回数量 (Optional[int])

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
