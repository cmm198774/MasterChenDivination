# MyAgent Memory Compacting 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 MyAgent 添加内存级别的 Memory 功能，通过 compacting 节点在对话结束前压缩历史消息，控制 token 数量。

**Architecture:** 在 LangGraph Agent 中添加 compacting 节点，位于 model 节点输出后、END 节点前。该节点会剔除 tool_calls 相关消息，保留 system prompt 和最新 AI 回复，对中间对话进行智能压缩（先总结，再截断），使用 MemorySaver 保存状态。

**Tech Stack:** LangGraph, LangChain Core, Python

---

## 文件结构

### 修改文件
- `MyAgent.py`: 核心修改文件
  - 添加 `count_tokens()` 函数（计算消息 token 数）
  - 添加 `summarize_messages()` 函数（调用 LLM 总结消息）
  - 添加 `compacting_node()` 函数（压缩消息逻辑）
  - 修改 `create_agent_graph()` 函数，添加 compacting 节点和 MemorySaver

### 新增文件
- 无（所有功能集成到 MyAgent.py）

---

### Task 1: 添加 token 计数功能

**Files:**
- Modify: `MyAgent.py:1-50`（文件顶部，导入部分）

- [ ] **Step 1: 添加必要的导入**

在 `MyAgent.py` 文件顶部添加以下导入：

```python
# 在现有导入后添加
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
import tiktoken  # 用于 token 计数
```

- [ ] **Step 2: 添加 token 计数函数**

在 `call_with_timeout()` 函数后（约第 45 行），添加 `count_tokens()` 函数：

```python
def count_tokens(messages: List[BaseMessage], model_name: str = "qwen3.6-flash") -> int:
    """
    计算消息列表的 token 总数。
    
    参数:
        messages: 消息列表
        model_name: 模型名称（用于选择正确的编码）
    
    返回:
        token 总数
    """
    try:
        # 使用 cl100k_base 编码（适用于大多数模型）
        enc = tiktoken.get_encoding("cl100k_base")
        
        total_tokens = 0
        for msg in messages:
            # 每条消息有固定的开销
            tokens = 4  # 消息格式开销
            if hasattr(msg, 'content') and msg.content:
                tokens += len(enc.encode(str(msg.content)))
            if hasattr(msg, 'role'):
                tokens += len(enc.encode(msg.role))
            total_tokens += tokens
        
        return total_tokens
    except Exception as e:
        print(f"  [DEBUG] Token 计算失败: {e}，使用估算值")
        # 降级：使用字符数估算（4 字符 ≈ 1 token）
        total_chars = sum(len(str(msg.content)) for msg in messages if hasattr(msg, 'content'))
        return total_chars // 4
```

- [ ] **Step 3: 验证代码语法**

运行：`python -m py_compile MyAgent.py`
预期：无错误输出

- [ ] **Step 4: 提交**

```bash
git add MyAgent.py
git commit -m "feat: 添加 token 计数功能"
```

---

### Task 2: 添加消息总结功能

**Files:**
- Modify: `MyAgent.py`（在 `count_tokens()` 函数后）

- [ ] **Step 1: 添加消息总结函数**

在 `count_tokens()` 函数后，添加 `summarize_messages()` 函数：

```python
def summarize_messages(
    messages: List[BaseMessage],
    llm,
    max_tokens: int = 500
) -> str:
    """
    调用 LLM 总结消息列表。
    
    参数:
        messages: 需要总结的消息列表
        llm: LLM 实例
        max_tokens: 总结的最大 token 数
    
    返回:
        总结文本
    """
    # 构建总结 prompt
    summary_prompt = """请总结以下对话内容，保留关键信息，用简洁的语言表达：

对话内容：
{dialogue}

请用 200 字以内总结："""
    
    # 提取对话内容
    dialogue_parts = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            dialogue_parts.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            dialogue_parts.append(f"助手: {msg.content}")
    
    dialogue = "\n".join(dialogue_parts)
    
    try:
        response = call_with_timeout(
            llm.invoke,
            timeout=10,
            input=[SystemMessage(content=summary_prompt.format(dialogue=dialogue))],
        )
        summary = response.content.strip() if hasattr(response, 'content') else ""
        print(f"  [DEBUG] 消息总结完成，长度: {len(summary)} 字符")
        return summary
    except Exception as e:
        print(f"  [DEBUG] 消息总结失败: {e}")
        return ""
```

- [ ] **Step 2: 验证代码语法**

运行：`python -m py_compile MyAgent.py`
预期：无错误输出

- [ ] **Step 3: 提交**

```bash
git add MyAgent.py
git commit -m "feat: 添加消息总结功能"
```

---

### Task 3: 添加 compacting 节点

**Files:**
- Modify: `MyAgent.py`（在 `summarize_messages()` 函数后）

- [ ] **Step 1: 添加 compacting 节点函数**

在 `summarize_messages()` 函数后，添加 `compacting_node()` 函数：

```python
def compacting_node(
    state: AgentState,
    llm,
    memory_token_limit: int = 2000
) -> dict:
    """
    压缩消息，保留关键信息，控制 token 数量。
    
    参数:
        state: 当前状态
        llm: LLM 实例
        memory_token_limit: 中间对话的 token 上限
    
    返回:
        更新后的状态
    """
    messages = list(state["messages"])
    
    if not messages:
        return {"messages": []}
    
    # 1. 提取 system prompt（第一条消息）
    system_msg = None
    start_idx = 0
    if isinstance(messages[0], SystemMessage):
        system_msg = messages[0]
        start_idx = 1
    
    # 2. 提取最新 AI 回复（最后一条消息）
    last_ai_msg = messages[-1] if messages else None
    
    # 3. 提取中间对话（排除 tool_calls 相关消息）
    middle_messages = []
    for i in range(start_idx, len(messages) - 1):
        msg = messages[i]
        
        # 跳过 AIMessage with tool_calls
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            continue
        
        # 跳过 ToolMessage
        if isinstance(msg, ToolMessage):
            continue
        
        middle_messages.append(msg)
    
    # 4. 计算中间对话的 token 数
    middle_tokens = count_tokens(middle_messages)
    print(f"  [DEBUG] 中间对话 token 数: {middle_tokens}, 阈值: {memory_token_limit}")
    
    # 5. 压缩策略
    if middle_tokens <= memory_token_limit:
        # 不超阈值，保留原样
        new_messages = []
        if system_msg:
            new_messages.append(system_msg)
        new_messages.extend(middle_messages)
        if last_ai_msg:
            new_messages.append(last_ai_msg)
    else:
        # 超阈值，需要压缩
        print(f"  [DEBUG] 中间对话超过阈值，开始压缩")
        
        # 5a. 调用 LLM 总结
        summary_text = summarize_messages(middle_messages, llm, max_tokens=500)
        
        if summary_text:
            # 总结成功，构建新的消息列表
            summary_msg = SystemMessage(content=f"[对话历史摘要] {summary_text}")
            
            # 检查总结后的 token 数
            summary_tokens = count_tokens([summary_msg])
            
            if summary_tokens > memory_token_limit:
                # 总结后仍然超过阈值，截断总结内容
                print(f"  [DEBUG] 总结后仍然超过阈值，截断总结")
                # 简单截断：保留前 memory_token_limit 个 token 对应的字符
                max_chars = memory_token_limit * 4  # 估算：1 token ≈ 4 字符
                truncated_summary = summary_text[:max_chars]
                summary_msg = SystemMessage(content=f"[对话历史摘要] {truncated_summary}")
            
            new_messages = []
            if system_msg:
                new_messages.append(system_msg)
            new_messages.append(summary_msg)
            if last_ai_msg:
                new_messages.append(last_ai_msg)
        else:
            # 总结失败，降级为直接截断
            print(f"  [DEBUG] 总结失败，降级为直接截断")
            # 保留最近的消息，直到 token 数低于阈值
            kept_messages = []
            current_tokens = 0
            
            for msg in reversed(middle_messages):
                msg_tokens = count_tokens([msg])
                if current_tokens + msg_tokens > memory_token_limit:
                    break
                kept_messages.insert(0, msg)
                current_tokens += msg_tokens
            
            new_messages = []
            if system_msg:
                new_messages.append(system_msg)
            new_messages.extend(kept_messages)
            if last_ai_msg:
                new_messages.append(last_ai_msg)
    
    print(f"  [DEBUG] Compacting 完成，消息数: {len(messages)} -> {len(new_messages)}")
    return {"messages": new_messages}
```

- [ ] **Step 2: 验证代码语法**

运行：`python -m py_compile MyAgent.py`
预期：无错误输出

- [ ] **Step 3: 提交**

```bash
git add MyAgent.py
git commit -m "feat: 添加 compacting 节点函数"
```

---

### Task 4: 修改 create_agent_graph 函数，添加 compacting 节点和 MemorySaver

**Files:**
- Modify: `MyAgent.py:52-293`（`create_agent_graph()` 函数）

- [ ] **Step 1: 添加新参数**

修改 `create_agent_graph()` 函数签名，添加 `memory_token_limit` 参数：

```python
def create_agent_graph(
    model_name: str = "qwen3.6-flash",
    base_url: str = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    api_key: str = "",
    temperature: float = 0.2,
    tool_list: List[BaseTool] = None,
    tool_descriptions: str = "",
    tool_timeout: int = 20,
    enable_mood_detection: bool = True,
    memory_token_limit: int = 2000,  # 新增参数
):
```

- [ ] **Step 2: 导入 MemorySaver**

在 `create_agent_graph()` 函数内部，添加 MemorySaver 的导入和初始化：

```python
# 在函数开头，创建 LLM 之前
from langgraph.checkpoint.memory import MemorySaver

# ... 现有代码 ...
```

- [ ] **Step 3: 创建 compacting 节点包装函数**

在 `create_agent_graph()` 函数内部（在 `timeout_tool_node = TimeoutToolNode(...)` 之后），创建 compacting 节点的包装函数：

```python
# 在 timeout_tool_node = TimeoutToolNode(tool_list, tool_timeout) 之后

# 创建 compacting 节点的包装函数（绑定 llm 和 memory_token_limit）
def compacting_wrapper(state: AgentState) -> dict:
    return compacting_node(state, llm, memory_token_limit)
```

- [ ] **Step 4: 修改图结构，添加 compacting 节点**

修改图结构的构建部分（约第 274-291 行），添加 compacting 节点：

```python
# 构建 graph
workflow = StateGraph(AgentState)

if enable_mood_detection:
    # 先检测情绪，再调用模型
    workflow.add_node("detect_mood", detect_mood)
    workflow.add_node("model", call_model)
    workflow.add_node("tools", timeout_tool_node)
    workflow.add_node("compacting", compacting_wrapper)  # 新增
    workflow.set_entry_point("detect_mood")
    workflow.add_edge("detect_mood", "model")
else:
    workflow.add_node("model", call_model)
    workflow.add_node("tools", timeout_tool_node)
    workflow.add_node("compacting", compacting_wrapper)  # 新增
    workflow.set_entry_point("model")

# 修改条件边：model 不再直接连接到 END，而是连接到 compacting
workflow.add_conditional_edges("model", should_end, {"tools": "tools", END: "compacting"})  # 修改：END -> compacting
workflow.add_edge("tools", "model")
workflow.add_edge("compacting", END)  # 新增：compacting -> END

# 使用 MemorySaver 编译
memory = MemorySaver()
return workflow.compile(checkpointer=memory)
```

- [ ] **Step 5: 验证代码语法**

运行：`python -m py_compile MyAgent.py`
预期：无错误输出

- [ ] **Step 6: 提交**

```bash
git add MyAgent.py
git commit -m "feat: 集成 compacting 节点和 MemorySaver 到 Agent 图"
```

---

### Task 5: 测试 Memory Compacting 功能

**Files:**
- Create: `test_memory_compacting.py`（测试文件）

- [ ] **Step 1: 创建测试文件**

创建 `test_memory_compacting.py`：

```python
"""
测试 Memory Compacting 功能
"""
from MyAgent import create_agent_graph
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool


@tool
def dummy_tool(x: str) -> str:
    """一个测试工具"""
    return f"Tool result: {x}"


def test_single_turn():
    """测试单轮对话（无工具调用）"""
    print("\n=== 测试 1: 单轮对话 ===")
    
    graph = create_agent_graph(
        model_name="qwen3.6-flash",
        api_key="your-api-key",
        tool_list=[],
        tool_descriptions="",
        memory_token_limit=2000,
    )
    
    config = {"configurable": {"thread_id": "test-1"}}
    
    result = graph.invoke(
        {"messages": [HumanMessage(content="你好")]},
        config=config
    )
    
    print(f"消息数: {len(result['messages'])}")
    for i, msg in enumerate(result['messages']):
        print(f"  [{i}] {type(msg).__name__}: {msg.content[:50]}...")
    
    print("✓ 单轮对话测试通过")


def test_multi_turn_with_tools():
    """测试多轮对话（有工具调用）"""
    print("\n=== 测试 2: 多轮对话（有工具） ===")
    
    graph = create_agent_graph(
        model_name="qwen3.6-flash",
        api_key="your-api-key",
        tool_list=[dummy_tool],
        tool_descriptions="你可以使用 dummy_tool 工具",
        memory_token_limit=2000,
    )
    
    config = {"configurable": {"thread_id": "test-2"}}
    
    # 第一轮
    result = graph.invoke(
        {"messages": [HumanMessage(content="使用 dummy_tool 测试")]},
        config=config
    )
    
    print(f"第一轮消息数: {len(result['messages'])}")
    
    # 第二轮
    result = graph.invoke(
        {"messages": [HumanMessage(content="继续对话")]},
        config=config
    )
    
    print(f"第二轮消息数: {len(result['messages'])}")
    for i, msg in enumerate(result['messages']):
        print(f"  [{i}] {type(msg).__name__}: {msg.content[:50] if hasattr(msg, 'content') else 'N/A'}...")
    
    print("✓ 多轮对话测试通过")


def test_long_conversation():
    """测试长对话（触发压缩）"""
    print("\n=== 测试 3: 长对话（触发压缩） ===")
    
    graph = create_agent_graph(
        model_name="qwen3.6-flash",
        api_key="your-api-key",
        tool_list=[],
        tool_descriptions="",
        memory_token_limit=500,  # 较低的阈值，容易触发压缩
    )
    
    config = {"configurable": {"thread_id": "test-3"}}
    
    # 模拟多轮对话
    for i in range(5):
        result = graph.invoke(
            {"messages": [HumanMessage(content=f"这是第 {i+1} 轮对话的内容")]},
            config=config
        )
        print(f"第 {i+1} 轮，消息数: {len(result['messages'])}")
    
    print("✓ 长对话测试通过")


if __name__ == "__main__":
    # 注意：需要替换为真实的 API key
    print("请确保已设置正确的 API key")
    test_single_turn()
    test_multi_turn_with_tools()
    test_long_conversation()
    print("\n=== 所有测试完成 ===")
```

- [ ] **Step 2: 运行测试**

```bash
# 先替换 test_memory_compacting.py 中的 "your-api-key" 为真实的 API key
# 然后运行：
python test_memory_compacting.py
```

预期：
- 测试 1：单轮对话，消息数较少
- 测试 2：多轮对话，工具调用相关消息被剔除
- 测试 3：长对话，触发压缩，消息数减少

- [ ] **Step 3: 提交测试文件**

```bash
git add test_memory_compacting.py
git commit -m "test: 添加 Memory Compacting 功能测试"
```

---

### Task 6: 更新文档

**Files:**
- Modify: `MyAgentReadMe.txt`

- [ ] **Step 1: 更新 README**

在 `MyAgentReadMe.txt` 中添加新功能的说明：

```
# 新功能：Memory Compacting

## 参数说明
- memory_token_limit: 中间对话的 token 上限，默认 2000 tokens
  - 当中间对话（排除 system prompt 和最新回复）的 token 数超过此值时，会触发压缩
  - 压缩策略：先调用 LLM 总结，如果总结后仍然超过阈值，则截断总结内容

## 使用示例
graph = create_agent_graph(
    model_name="qwen3.6-flash",
    api_key="your-api-key",
    memory_token_limit=2000,  # 可选，默认 2000
)

# 使用 config 指定 thread_id
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": [...]}, config=config)

## 工作原理
1. 每次对话结束前，compacting 节点会：
   - 剔除 tool_calls 相关消息
   - 保留 system prompt 和最新 AI 回复
   - 对中间对话进行压缩（如果超过 token 阈值）
2. MemorySaver 会保存压缩后的状态
3. 下次对话时，会自动加载历史状态
```

- [ ] **Step 2: 提交**

```bash
git add MyAgentReadMe.txt
git commit -m "docs: 更新 Memory Compacting 功能说明"
```

---

## 自审清单

- [x] **Spec 覆盖检查：** 所有需求都已实现
  - ✅ MemorySaver 内存级别记忆
  - ✅ Token 限制
  - ✅ compacting 节点
  - ✅ 剔除 tool_calls 消息
  - ✅ 保留 system prompt 和最新回复
  - ✅ 先总结再截断的压缩策略

- [x] **占位符扫描：** 无 TBD、TODO

- [x] **类型一致性：** 
  - `count_tokens()` 函数签名一致
  - `summarize_messages()` 函数签名一致
  - `compacting_node()` 函数签名一致
  - `memory_token_limit` 参数名一致

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-03-memory-compacting.md`**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
