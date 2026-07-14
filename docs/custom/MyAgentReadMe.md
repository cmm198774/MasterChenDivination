#MyAgent.py中
创建Agent函数 create_agent_graph
输入model_name,base_url,api_key,temperature这四个参数指定需要调用的大模型
tool_list:指定需要调用的工具列表
tool_description:指定工具列表的描述
tool_timeout:工具调用的最大时间
memory_token_limit: 中间对话的 token 上限，默认 2000 tokens
（system_prompt 已内置算命先生角色设定）

返回compile之后的graph（已集成 MemorySaver 和 compacting 节点）


# 新功能：Memory Compacting

## 功能说明
1. 使用 MemorySaver 进行内存级别的对话状态保存
2. 在对话结束前（END 节点前）自动压缩历史消息，控制 token 数量
3. 压缩策略：先调用 LLM 总结，如果总结后仍然超过阈值，则截断总结内容

## 工作原理
1. 每次对话结束前，compacting 节点会：
   - 剔除 tool_calls 相关消息（AIMessage with tool_calls, ToolMessage）
   - 保留 system prompt 和最新 AI 回复
   - 对中间对话进行压缩（如果超过 token 阈值）
2. MemorySaver 会保存压缩后的状态
3. 下次对话时，会自动加载历史状态

## 使用示例
```python
graph = create_agent_graph(
    model_name="qwen3.6-flash",
    api_key="your-api-key",
    memory_token_limit=2000,  # 可选，默认 2000
)

# 使用 config 指定 thread_id
config = {"configurable": {"thread_id": "user-123"}}
result = graph.invoke({"messages": [...]}, config=config)
```


#server.py中
然后server.py里面qingxu_chain以及run里面都直接调用这个生成的agent
大模型使用qwen3.6-flash