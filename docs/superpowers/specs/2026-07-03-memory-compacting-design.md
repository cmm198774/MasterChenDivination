# MyAgent Memory Compacting 设计文档

## 概述
为 MyAgent 添加内存级别的 Memory 功能，通过 compacting 节点在对话结束前压缩历史消息，控制 token 数量。

## 需求
1. 使用 MemorySaver 进行内存级别的记忆保存
2. 限制 memory 的 token 数量，避免超出模型上下文限制
3. 在 model 节点输出后、END 节点前插入 compacting 节点
4. 对 messages 进行智能压缩，保留关键信息

## 架构设计

### 图结构
```
用户输入 → detect_mood → model → [是否调用工具？]
                                      ↓ 是
                                    tools → model → ...
                                      ↓ 否
                                   compacting → END
```

### Compacting 节点逻辑

**输入：** AgentState（包含 messages 列表）

**处理步骤：**
1. 提取需要保留的消息：
   - SystemMessage（系统提示）
   - AIMessage（最新回复，messages[-1]）

2. 提取中间对话（排除 tool_calls 相关消息）：
   - 剔除 AIMessage with tool_calls
   - 剔除 ToolMessage

3. 计算中间对话的 token 数量

4. 压缩策略（方案 C1：先总结，再截断）：
   - 如果中间对话 token < 阈值：保留原样
   - 如果中间对话 token >= 阈值：
     a. 调用 LLM 总结中间对话
     b. 如果总结后仍然超过阈值，截断总结内容
     c. 用总结替换原始中间对话

5. 重新构建 messages：
   ```python
   new_messages = [system_msg, summary, last_ai_msg]
   ```

**输出：** 更新后的 AgentState

### 参数配置
- `memory_token_limit`: 中间对话的 token 上限，默认 2000 tokens
- 可根据模型上下文窗口调整

## 数据流

### 单轮对话（无工具调用）
```
1. 用户输入 → HumanMessage
2. detect_mood → 情绪识别
3. model → AIMessage（回复）
4. compacting:
   - 提取 system_msg + last_ai_msg
   - 中间对话为空或 token 较少
   - 直接保留
5. MemorySaver 保存状态
6. END
```

### 多轮对话（有工具调用）
```
1. 用户输入 → HumanMessage
2. detect_mood → 情绪识别
3. model → AIMessage（带 tool_calls）
4. tools → ToolMessage（工具结果）
5. model → AIMessage（最终回复）
6. compacting:
   - 提取 system_msg + last_ai_msg
   - 剔除 AIMessage(tool_calls) + ToolMessage
   - 如果中间对话 token 超过阈值，压缩
7. MemorySaver 保存状态
8. END
```

### 长对话（多轮累积）
```
1. 历史消息已保存在 MemorySaver
2. 新的用户输入 → HumanMessage
3. detect_mood → 情绪识别
4. model → AIMessage
5. compacting:
   - 提取 system_msg + last_ai_msg
   - 中间对话包含历史消息 + 当前轮对话
   - 如果 token 超过阈值，调用 LLM 总结
6. MemorySaver 保存压缩后的状态
7. END
```

## 错误处理

### LLM 总结失败
- 如果调用 LLM 总结失败，降级为直接截断
- 记录错误日志

### Token 计算失败
- 如果 token 计算失败，使用消息数量作为备选策略
- 默认保留最近 10 条消息

## 测试策略

### 单元测试
1. 测试 compacting 节点的消息提取逻辑
2. 测试 token 计算准确性
3. 测试压缩策略（不超阈值、超阈值）

### 集成测试
1. 测试单轮对话（无工具调用）
2. 测试多轮对话（有工具调用）
3. 测试长对话（触发压缩）

### 性能测试
1. 测试 compacting 节点的延迟
2. 测试 token 限制效果

## 实现文件

### 修改文件
- `MyAgent.py`:
  - 添加 `compacting_node` 函数
  - 修改图结构，在 END 前插入 compacting 节点
  - 添加 MemorySaver 支持
  - 添加 `memory_token_limit` 参数

### 新增文件
- 无（所有功能集成到 MyAgent.py）

## 依赖

### Python 库
- `langgraph.checkpoint.memory.MemorySaver`
- `langchain_core.messages`（已有）
- `tiktoken` 或其他 token 计数库（可选）

### 模型
- qwen3.6-flash（或其他支持的模型）

## 成功标准
1. compacting 节点能够正确提取和压缩消息
2. MemorySaver 能够保存和恢复对话状态
3. 长对话能够自动触发压缩
4. 压缩后的对话保留关键信息
5. 性能可接受（compacting 节点延迟 < 2 秒）

## 未来扩展
1. 支持持久化存储（SQLite、Redis）
2. 支持多种压缩策略（用户可选择）
3. 支持自定义压缩 prompt
4. 支持情绪历史的保留
