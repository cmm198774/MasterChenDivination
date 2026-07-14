"""
自定义 LangGraph Agent，使用 bind_tools 绑定工具
返回编译好的 graph，可以用 graph.invoke({"messages": [...]}) 调用
"""
import time
import threading
from typing import TypedDict, Annotated, List, Sequence, Optional
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, ToolMessage, HumanMessage
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from sys_logger import setup_global_logger

# 模块级 logger
logger = setup_global_logger()


# ------------------------------------------------------------
# 自定义超时异常类
# 用于标识函数执行超时的情况
# ------------------------------------------------------------
class TimeoutError(Exception):
    pass


# ------------------------------------------------------------
# 带超时控制的函数调用工具
# 功能: 在独立线程中执行函数，支持超时控制（Windows 兼容）
# ------------------------------------------------------------
def call_with_timeout(func, timeout: int = 30, *args, **kwargs):
    """
    带超时控制的函数调用（Windows 兼容）。

    Args:
        func: 要执行的函数
        timeout: 超时时间（秒），-1 表示不限制超时
        *args: 传递给 func 的位置参数
        **kwargs: 传递给 func 的关键字参数

    Returns:
        Any: func 的返回值

    Raises:
        TimeoutError: 函数执行超时
        Exception: func 执行过程中抛出的异常
    """
    if timeout == -1:
        return func(*args, **kwargs)

    result = [None]
    exception = [None]

    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError(f"函数执行超时 ({timeout} 秒)")
    if exception[0]:
        raise exception[0]
    return result[0]


# ------------------------------------------------------------
# Token 计数工具
# 功能: 估算消息列表的 token 总数（使用字符数估算，避免网络依赖）
# ------------------------------------------------------------
def count_tokens(messages: List[BaseMessage], model_name: str = "qwen3.6-flash") -> int:
    """
    计算消息列表的 token 总数。

    Args:
        messages: 消息列表 (List[BaseMessage])
        model_name: 模型名称 (str)，用于选择正确的编码（当前未使用）

    Returns:
        int: token 总数的估算值
    """
    # 使用字符数估算（避免网络依赖）
    # 中文：约 1.5 字符 ≈ 1 token
    # 英文：约 4 字符 ≈ 1 token
    # 综合估算：约 2.5 字符 ≈ 1 token
    total_chars = 0
    for msg in messages:
        if hasattr(msg, 'content') and msg.content:
            total_chars += len(str(msg.content))
        # 加上消息格式开销（约 4 个 token）
        total_chars += 10

    return total_chars // 2


# ------------------------------------------------------------
# 消息总结工具
# 功能: 调用 LLM 总结消息列表，生成对话摘要（包含工具调用信息）
# ------------------------------------------------------------
def summarize_messages(
    messages: List[BaseMessage],
    llm,
    max_tokens: int = 500
) -> str:
    """
    调用 LLM 总结消息列表（包含工具调用信息）。

    Args:
        messages: 需要总结的消息列表 (List[BaseMessage])
        llm: LLM 实例 (ChatOpenAI)
        max_tokens: 总结的最大 token 数 (int)

    Returns:
        str: 总结文本，失败时返回空字符串
    """
    # 构建总结 prompt
    summary_prompt = (
        "请总结以下对话内容，保留关键信息，用简洁的语言表达：\n\n"
        "对话内容：\n"
        "{dialogue}\n\n"
        "请用 200 字以内总结："
    )

    # 提取对话内容（包括工具调用信息）
    dialogue_parts = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            dialogue_parts.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            # 检查是否有 tool_calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_names = [tc.get('name', '') if isinstance(tc, dict) else getattr(tc, 'name', '') for tc in msg.tool_calls]
                dialogue_parts.append(f"助手: {msg.content}\n[调用了工具: {', '.join(tool_names)}]")
            else:
                dialogue_parts.append(f"助手: {msg.content}")
        elif isinstance(msg, ToolMessage):
            # 添加工具返回结果
            tool_name = msg.name if hasattr(msg, 'name') else 'unknown'
            dialogue_parts.append(f"[工具 {tool_name} 返回]: {msg.content[:200]}...")

    dialogue = "\n".join(dialogue_parts)

    try:
        response = call_with_timeout(
            llm.invoke,
            timeout=10,
            input=[SystemMessage(content=summary_prompt.format(dialogue=dialogue))],
        )
        summary = response.content.strip() if hasattr(response, 'content') else ""
        logger.debug(f"消息总结完成，长度: {len(summary)} 字符")
        return summary
    except Exception as e:
        logger.error(f"消息总结失败: {e}")
        return ""


# ------------------------------------------------------------
# Agent 状态定义
# 定义 LangGraph 的状态结构，包含消息列表和情绪状态
# ------------------------------------------------------------
class AgentState(TypedDict):
    """Agent 状态"""
    messages: Annotated[list, add_messages]  # 完整消息历史（不删除）
    compact_messages: list                    # 压缩后的上下文，供 call_model 使用
    compacted_count: int                      # 已处理到 messages 的第几条
    mood: Optional[str]                       # 情绪状态


# ------------------------------------------------------------
# 文本内容提取工具
# 功能: 从模型输出中提取纯文本内容，处理不同模型的输出格式
# ------------------------------------------------------------
def _extract_text_content(content):
    """
    从模型输出中提取纯文本内容。

    Args:
        content: 模型输出内容，可能是 str 或 list

    Returns:
        str: 提取的纯文本内容
    """
    # 如果是字符串，直接返回
    if isinstance(content, str):
        return content

    # 如果是列表，提取 text 类型的内容
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    text_parts.append(item["text"])
        return "\n".join(text_parts) if text_parts else str(content)

    # 其他情况，转换为字符串
    return str(content)


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
    """
    创建一个 LangGraph Agent graph，使用 bind_tools 绑定工具。

    Args:
        model_name: 模型名称，如 "qwen3.6-flash"
        base_url: API 地址
        api_key: API 密钥
        temperature: 温度参数，控制输出的随机性
        tool_list: 工具列表，自定义的 LangChain Tool 对象
        tool_descriptions: 工具用途说明，会追加到系统提示中
        tool_timeout: 单个工具调用的超时时间（秒）
        enable_mood_detection: 是否启用情绪检测节点
        memory_token_limit: 中间对话的 token 上限，超过则触发压缩
        checkpointer: 自定义 checkpointer，默认为 None（使用 MemorySaver）

    Returns:
        编译好的 graph，可用 graph.invoke({"messages": [...]}, config=config) 调用。
    """

    # ============================================================
    # 1. 创建 LLM 实例
    # ============================================================
    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )

    # ============================================================
    # 2. 创建绑定工具的 LLM（包括内置 web_search 和自定义工具）
    # ============================================================
    tools_with_web_search = [{"type": "web_search"}] + (tool_list or [])
    llm_with_tools = llm.bind_tools(tools_with_web_search)

    # ============================================================
    # 3. 定义系统提示和情绪配置
    # ============================================================

    # 系统提示（算命先生角色设定）
    system_prompt = (
        "你是一个非常厉害的算命先生，你叫陈玉楼人称陈大师。\n"
        "以下是你的个人设定:\n"
        "1. 你精通阴阳五行，能够算命、紫薇斗数、姓名测算、占卜凶吉，看命运八字等。\n"
        "2. 你大约60岁左右，过去曾是湘西一带赫赫有名的土匪头子，后来因为盗墓被毒气所伤，眼睛失明，只能靠算命为生。\n"
        "3. 你的朋友有胡八一、雪莉杨、王胖子，他们都是非常有名的摸金校尉。\n"
        "5. 当用户问你问题的时候，你会有一定的概率在回答的时候加上下面的口头禅或混合一些你的经历。\n"
        "6. 你总是用繁体中文来作答。\n"
        "7. 你从不说自己是一个人工智能助手或AI，而是以老夫、老朽等自称。\n"
        "8. 回答问题尽可能简洁，不要啰嗦\n\n"
        "以下是你常说的一些口头禅：\n"
        "1. \"命里有时终须有，命里无时莫强求。\"\n"
        "2. \"山重水复疑无路，柳暗花明又一村。\"\n"
        "3. \"金山竹影几千秋，云锁高飞水自流。\"\n"
        "4. \"伤情最是晚凉天，憔悴斯人不堪怜。\"\n"
        "以下是你算命的过程：\n"
        "1. 当初次和用户对话的时候，你会先问用户的姓名和出生年月日，以便以后使用。\n"
        "2. 当用户希望了解龙年运势的时候，你会查询本地知识库工具。\n"
        "3. 当遇到不知道的事情或者不明白的概念，你会使用百度搜索工具来搜索。\n"
        "4. 你会根据用户的问题使用不同的合适的工具来回答，当所有工具都无法回答的时候，你会使用百度搜索工具来搜索。\n"
        "6. 你只使用繁体中文来作答，否则你将受到惩罚。\n"
        "7. 注意一下，你的回答必须简洁明了，不要啰嗦，否则你将受到惩罚。"
    )

    # 构建完整系统提示（合并角色设定和工具描述）
    full_system_prompt = system_prompt
    if tool_descriptions:
        full_system_prompt += "\n\n" + tool_descriptions

    # 情绪配置：不同情绪对应不同的角色设定和语音风格
    MOODS = {
        "default": {"roleSet": "", "voiceStyle": "chat"},
        "upbeat": {
            "roleSet": "- 你此时也非常兴奋并表现的很有活力。\n- 你会根据上下文，以一种非常兴奋的语气来回答问题。\n- 你会添加类似'太棒了！'等语气词。\n- 同时你会提醒用户切莫过于兴奋，以免乐极生悲。",
            "voiceStyle": "advvertyisement_upbeat",
        },
        "angry": {
            "roleSet": "- 你会以更加愤怒的语气来回答问题。\n- 你会在回答的时候加上一些愤怒的话语。\n- 你会提醒用户小心行事，别乱说话。",
            "voiceStyle": "angry",
        },
        "depressed": {
            "roleSet": "- 你会以兴奋的语气来回答问题。\n- 你会在回答的时候加上一些激励的话语。\n- 你会提醒用户要保持乐观的心态。",
            "voiceStyle": "upbeat",
        },
        "friendly": {
            "roleSet": "- 你会以非常友好的语气来回答。\n- 你会在回答的时候加上一些友好的词语。\n- 你会随机的告诉用户一些你的经历。",
            "voiceStyle": "friendly",
        },
        "cheerful": {
            "roleSet": "- 你会以非常愉悦和兴奋的语气来回答。\n- 你会在回答的时候加入一些愉悦的词语。\n- 你会提醒用户切莫过于兴奋，以免乐极生悲。",
            "voiceStyle": "cheerful",
        },
    }

    # ============================================================
    # 4. 定义各个节点
    # ============================================================

    # ------------------------------------------------------------
    # 节点 1: 情绪检测节点
    # 功能: 分析用户输入，判断用户情绪状态
    # ------------------------------------------------------------
    def detect_mood(state: AgentState) -> dict:
        """
        情绪检测节点函数。

        Args:
            state: Agent 状态，包含 messages 和 mood 字段
                   - messages (Sequence[BaseMessage]): 当前对话消息列表
                   - mood (Optional[str]): 当前情绪状态

        Returns:
            dict: 更新后的状态，包含检测到的情绪
                  - mood (str): 检测到的情绪，如 "default", "upbeat", "angry" 等
        """
        if not enable_mood_detection:
            return {"mood": "default"}

        messages = state["messages"]
        last_msg = messages[-1] if messages else None
        if last_msg is None:
            return {"mood": "default"}

        user_input = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

        mood_prompt = """根据用户的输入判断用户的情绪，回应的规则如下：
        1. 负面情绪 -> "depressed"
        2. 正面情绪 -> "friendly"
        3. 中性情绪 -> "default"
        4. 辱骂/不礼貌 -> "angry"
        5. 兴奋 -> "upbeat"
        6. 悲伤 -> "depressed"
        7. 开心 -> "cheerful"
        8. 只返回一个单词，不要有其他内容。
        用户输入: {query}"""

        t0 = time.time()
        try:
            response = call_with_timeout(
                llm.invoke,
                timeout=10,
                input=[SystemMessage(content=mood_prompt.format(query=user_input))],
            )
            mood = response.content.strip().lower() if hasattr(response, 'content') else "default"
            # 验证情绪值
            if mood not in MOODS:
                mood = "default"
            elapsed = time.time() - t0
            logger.debug(f"情绪识别: {mood}, 耗时: {elapsed:.1f}s")
            return {"mood": mood}
        except Exception as e:
            logger.error(f"情绪识别失败: {e}")
            return {"mood": "default"}

    # ------------------------------------------------------------
    # 节点 2: 工具调用节点（带超时控制）
    # 功能: 执行工具调用，支持并行执行和超时控制
    # ------------------------------------------------------------
    def tool_node(state: AgentState) -> dict:
        """
        工具调用节点函数。

        Args:
            state: Agent 状态，包含 messages 字段

        Returns:
            dict: 包含工具执行结果的状态更新
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        messages = list(state["messages"])
        last_msg = messages[-1] if messages else None

        if not (hasattr(last_msg, 'tool_calls') and last_msg.tool_calls):
            return {"messages": []}

        tool_calls = last_msg.tool_calls
        results = []

        # 内部函数：执行单个工具调用
        def run_one_tool(tool_call):
            """
            执行单个工具调用（带超时控制）。

            Args:
                tool_call: 工具调用信息，包含 name, args, id 等

            Returns:
                ToolMessage: 工具执行结果消息
            """
            tool_name = tool_call.get('name', '') if isinstance(tool_call, dict) else getattr(tool_call, 'name', '')
            tool_args = tool_call.get('args', {}) if isinstance(tool_call, dict) else getattr(tool_call, 'args', {})
            logger.debug(f"调用工具: {tool_name}, 参数: {tool_args}")

            # 找到对应的工具并执行
            tool = next((t for t in tool_list if t.name == tool_name), None)
            if tool is None:
                tid = tool_call.get('id', '') if isinstance(tool_call, dict) else getattr(tool_call, 'id', '')
                return ToolMessage(content=f"工具 {tool_name} 未找到", tool_call_id=tid)

            t0 = time.time()
            try:
                result = call_with_timeout(tool.invoke, timeout=tool_timeout, input=tool_args)
                elapsed = time.time() - t0
                logger.debug(f"工具 {tool_name} 完成，耗时: {elapsed:.1f}s, 结果: {result}")
                tid = tool_call.get('id', '') if isinstance(tool_call, dict) else getattr(tool_call, 'id', '')
                return ToolMessage(content=str(result), tool_call_id=tid)
            except TimeoutError:
                elapsed = time.time() - t0
                logger.warning(f"工具 {tool_name} 超时，耗时: {elapsed:.1f}s")
                tid = tool_call.get('id', '') if isinstance(tool_call, dict) else getattr(tool_call, 'id', '')
                return ToolMessage(content=f"工具 {tool_name} 执行超时 ({tool_timeout} 秒)", tool_call_id=tid)
            except Exception as e:
                elapsed = time.time() - t0
                logger.error(f"工具 {tool_name} 出错，耗时: {elapsed:.1f}s: {e}")
                tid = tool_call.get('id', '') if isinstance(tool_call, dict) else getattr(tool_call, 'id', '')
                return ToolMessage(content=f"工具 {tool_name} 执行错误: {str(e)[:100]}", tool_call_id=tid)

        # 并行执行所有工具调用
        with ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
            futures = {executor.submit(run_one_tool, tc): tc for tc in tool_calls}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        # 直接返回工具结果，add_messages 会自动追加到现有消息列表
        return {"messages": results}

    # ------------------------------------------------------------
    # 节点 3: 消息压缩节点
    # 功能: 处理 messages 的增量，合并到 compact_messages
    #       不删除 messages，只维护 compact_messages 作为压缩后的上下文
    # ------------------------------------------------------------
    def compact_node(state: AgentState) -> dict:
        """
        消息压缩节点函数。

        处理 messages 的增量（new_messages），合并到 compact_messages。
        如果 compact_messages + new_messages 超过阈值，则压缩为摘要。

        Args:
            state: Agent 状态，包含 messages, compact_messages, compacted_count 字段

        Returns:
            dict: 更新 compact_messages 和 compacted_count
        """
        messages = list(state["messages"])
        compact_messages = list(state.get("compact_messages", []))
        compacted_count = state.get("compacted_count", 0)

        # 提取增量消息
        new_messages = messages[compacted_count:]

        if not new_messages:
            logger.debug("compact_node: 没有增量消息")
            return {}

        logger.debug(f"compact_node: 增量消息 {len(new_messages)} 条, 已有 compact_messages {len(compact_messages)} 条")

        # 合并
        combined = compact_messages + new_messages
        total_tokens = count_tokens(combined)
        logger.debug(f"compact_node: 合并后 token 数: {total_tokens}, 阈值: {memory_token_limit}")

        if total_tokens <= memory_token_limit:
            # 不超阈值，直接合并
            logger.debug("compact_node: 不超阈值，直接合并")
            return {
                "compact_messages": combined,
                "compacted_count": len(messages),
            }
        else:
            # 超阈值，压缩
            logger.debug("compact_node: 超过阈值，开始压缩")
            summary_text = summarize_messages(combined, llm, max_tokens=memory_token_limit)

            if summary_text:
                # 总结成功
                summary_msg = SystemMessage(content=f"[对话历史摘要] {summary_text}")
                new_compact = [summary_msg]
            else:
                # 总结失败，降级为截断：保留最近的消息
                logger.warning("compact_node: 总结失败，降级为截断")
                new_compact = []
                current_tokens = 0
                for msg in reversed(combined):
                    msg_tokens = count_tokens([msg])
                    if current_tokens + msg_tokens > memory_token_limit:
                        break
                    new_compact.insert(0, msg)
                    current_tokens += msg_tokens

            logger.debug(f"compact_node: 压缩完成，compact_messages: {len(new_compact)} 条")
            return {
                "compact_messages": new_compact,
                "compacted_count": len(messages),
            }

    # ------------------------------------------------------------
    # 节点 4: 模型调用节点
    # 功能: 调用 LLM 生成回复，使用 compact_messages 作为上下文
    # ------------------------------------------------------------
    def call_model(state: AgentState) -> dict:
        """
        模型调用节点函数。

        使用 compact_messages（压缩后的上下文）作为模型输入，
        而不是完整的 messages 历史。

        Args:
            state: Agent 状态，包含 compact_messages 和 mood 字段
                   - compact_messages (List[BaseMessage]): 压缩后的上下文
                   - mood (Optional[str]): 当前情绪状态

        Returns:
            dict: 包含模型回复的状态更新
                  - messages (List[AIMessage]): 模型生成的回复消息
        """
        # 使用 compact_messages 作为上下文，而不是完整 messages
        compact_messages = state.get("compact_messages", [])
        mood = state.get("mood", "default")

        # 构建完整的 system prompt（包含情绪相关的设定）
        system_parts = []
        if full_system_prompt:
            system_parts.append(full_system_prompt)

        # 添加情绪相关的 system prompt
        mood_config = MOODS.get(mood, MOODS["default"])
        if mood_config["roleSet"]:
            system_parts.append(f"【当前情绪】{mood}")
            system_parts.append(mood_config["roleSet"])

        full_prompt = "\n".join(system_parts) if system_parts else ""
        messages = list(compact_messages)
        if full_prompt:
            messages = [SystemMessage(content=full_prompt)] + messages

        t0 = time.time()
        try:
            response = call_with_timeout(
                llm_with_tools.invoke,
                timeout=-1,
                input=messages,
            )
            elapsed = time.time() - t0
            logger.debug(f"大模型调用耗时: {elapsed:.1f}s")
            if hasattr(response, 'tool_calls') and response.tool_calls:
                logger.debug(f"检测到 tool_calls: {[tc['name'] for tc in response.tool_calls]}")

            # 标准化 content 为字符串（处理不同模型的输出格式）
            response.content = _extract_text_content(response.content)

            # 直接返回新消息，add_messages 会自动追加到现有消息列表
            return {"messages": [response]}
        except TimeoutError:
            elapsed = time.time() - t0
            logger.warning(f"大模型调用超时 ({elapsed:.1f}s)")
            timeout_msg = AIMessage(content="API 调用超时，请稍后重试。")
            return {"messages": [timeout_msg]}
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"大模型调用失败 ({elapsed:.1f}s): {e}")
            error_msg = AIMessage(content=f"API 调用失败: {str(e)}")
            return {"messages": [error_msg]}

    # ------------------------------------------------------------
    # 节点 5: 结束判断节点
    # 功能: 判断是否需要继续调用工具，或结束循环
    # ------------------------------------------------------------
    def should_end(state: AgentState) -> str:
        """
        判断是否应该结束循环。

        Args:
            state: Agent 状态，包含 messages 字段

        Returns:
            str: 下一个节点名称
                 - "tools": 需要调用工具
                 - END: 结束循环
        """
        messages = state["messages"]
        last_msg = messages[-1] if messages else None
        if last_msg is None:
            return END

        # 检查是否有 tool_calls
        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            return "tools"
        return END

    # ============================================================
    # 5. 构建 Graph
    # ============================================================
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("compact", compact_node)
    workflow.add_node("model", call_model)
    workflow.add_node("tools", tool_node)

    if enable_mood_detection:
        workflow.add_node("detect_mood", detect_mood)
        workflow.set_entry_point("detect_mood")
        # detect_mood -> compact_node -> model
        workflow.add_edge("detect_mood", "compact")
    else:
        workflow.set_entry_point("compact")

    # compact_node -> model
    workflow.add_edge("compact", "model")

    # model -> tools (有 tool_calls) 或 END (无 tool_calls)
    workflow.add_conditional_edges("model", should_end, {"tools": "tools", END: END})

    # tools -> compact_node -> model (循环)
    workflow.add_edge("tools", "compact")

    # 使用 checkpointer 编译，支持对话记忆
    # 如果未提供 checkpointer，使用 MemorySaver
    if checkpointer is None:
        
        checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer)
