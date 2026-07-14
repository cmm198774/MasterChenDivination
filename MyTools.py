import os
import sys
import ssl

# 修复 Windows SSL 证书问题：跳过损坏的 Windows 证书存储，使用 certifi 证书
if sys.platform == "win32":
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    except ImportError:
        pass
    if hasattr(ssl.SSLContext, "_load_windows_store_certs"):
        ssl.SSLContext._load_windows_store_certs = lambda self, storename, purpose: None

import requests
from langchain_core.tools import tool
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_community.document_loaders import WebBaseLoader
from typing import List
from langchain_core.documents import Document
from sys_logger import setup_global_logger
from bs4 import BeautifulSoup
from config import (
    DASHSCOPE_API_KEY,
    BAIDU_AI_SEARCH_API_KEY,
    YUANFENJU_API_KEY,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL_NAME,
    EMBEDDING_MODEL,
    QDRANT_BASE_DIR,
    QDRANT_COLLECTION,
    TTS_MODEL,
    TTS_VOICE,
)
# 模块级 logger
logger = setup_global_logger()

# Mood to TTS instruction mapping for Qwen3-TTS
MOOD_TO_INSTRUCTION = {
    "default": "语速适中偏快，用平静、沉稳的语气说话，像一位经验丰富的算命先生。",
    "upbeat": "语速较快，用兴奋、激动的语气说话，表现出热情和活力。",
    "angry": "语速较快，用愤怒、严厉的语气说话，表现出不满和警告。",
    "depressed": "语速适中，用悲伤、低沉的语气说话，表现出忧虑和同情。",
    "friendly": "语速适中偏快，用友好、温和的语气说话，表现出亲切和关怀。",
    "cheerful": "语速较快，用开心、愉悦的语气说话，表现出高兴和乐观。",
}

# 工具描述
TOOL_DESCRIPTIONS = """【可用工具】
- get_info_from_local_db: 查询本地知识库，用于回答2026年或者马年运势相关问题。(参数: query=用户问题)
- search_tool: 百度搜索实时资讯，用于搜索未知信息、新闻、天气、股票等。(参数: query=搜索关键词)
- bazi_cesuan: 八字排盘测算，用于查询用户的八字信息。需要提供姓名和出生年月日时。(参数: query=姓名和出生信息)
- yaoyigua: 摇卦占卜抽签工具，用于周易摇卦占卜。(无参数)
- jiemeng: 周公解梦工具，用于解析梦境内容。(参数: query=梦境内容描述)
根据用户问题选择合适的工具调用，不要重复调用同一个工具。"""

# 全局 retriever 和 client，单例模式
_retriever = None
_qdrant_client = None

def _get_retriever(file_name: str ) -> Qdrant:
    global _retriever, _qdrant_client
    if _retriever is None:
        _qdrant_client = QdrantClient(path=QDRANT_BASE_DIR, prefer_grpc=False)
        store = Qdrant(
            _qdrant_client,
            file_name,
            DashScopeEmbeddings(
                model=EMBEDDING_MODEL,
                dashscope_api_key=DASHSCOPE_API_KEY,
            ),
        )
        _retriever = store.as_retriever(search_type="mmr")
    return _retriever

# ==========================================
# HTML 加载器
# ==========================================

def load_html(source: str) -> List[Document]:
    """
    加载 HTML 内容，支持本地文件和远程 URL。

    Args:
        source: HTML 文件路径或 URL (str)

    Returns:
        List[Document]: 文档列表
    """
    logger.info(f"加载 HTML: {source}")

    try:
        if source.startswith("http://") or source.startswith("https://"):
            # 远程 URL
            loader = WebBaseLoader(source)
            docs = loader.load()
        else:
            # 本地文件，手动读取并解析
            with open(source, "r", encoding="utf-8") as f:
                html_content = f.read()

            # 使用 BeautifulSoup 提取文本
 
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

            # 创建 Document
            doc = Document(page_content=text, metadata={"source": source})
            docs = [doc]

        logger.info(f"成功加载 {len(docs)} 个文档")
        return docs
    except Exception as e:
        logger.error(f"加载 HTML 失败: {e}")
        raise


# ==========================================
# URL 批量处理：添加到 Qdrant 数据库
# ==========================================

def add_urls_to_db(urls: List[str], collection_name: str = "yunshi_2026") -> dict:
    """
    将 URL 列表的内容添加到 Qdrant 数据库。

    该函数遍历 URL 列表（支持本地文件路径和远程 URL），对每个 URL：
    1. 加载 HTML 内容
    2. 使用递归字符分割器切分文本块
    3. 向量化后追加到指定的 Qdrant collection

    Args:
        urls: URL 列表，可以是本地路径或远程 URL (List[str])
        collection_name: Qdrant collection 名称 (str)，默认 "yunshi_2026"

    Returns:
        dict: 包含处理结果的字典
            - success: List[str] 成功处理的 URL
            - failed: List[dict] 失败的 URL 及原因
            - total_chunks: int 总文本块数
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    logger.info(f"开始处理 {len(urls)} 个 URL，目标 collection: {collection_name}")

    # 配置文本块大小和重叠
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 100

    # 初始化 embedding 模型
    embeddings = DashScopeEmbeddings(
        model=EMBEDDING_MODEL,
        dashscope_api_key=DASHSCOPE_API_KEY,
    )

    # 初始化 Qdrant 客户端
    qdrant_client = QdrantClient(path=QDRANT_BASE_DIR, prefer_grpc=False)

    # 初始化文本分割器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )

    # Ensure collection exists with correct vector dimensions BEFORE the loop.
    # This avoids the pickle error from Qdrant.from_documents() and handles
    # dimension mismatches from previous runs with different embedding models.
    expected_vector_size = 1024  # text-embedding-v3 default dimension
    collections = qdrant_client.get_collections().collections
    collection_names = [c.name for c in collections]

    if collection_name in collection_names:
        # Check existing collection's vector size
        info = qdrant_client.get_collection(collection_name)
        actual_size = info.config.params.vectors.size
        if actual_size != expected_vector_size:
            logger.warning(
                f"Collection {collection_name} has vector size {actual_size}, "
                f"expected {expected_vector_size}. Recreating."
            )
            qdrant_client.delete_collection(collection_name)
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=expected_vector_size, distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info(f"Recreated collection: {collection_name}")
        else:
            logger.info(f"Using existing collection: {collection_name}")
    else:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=expected_vector_size, distance=qmodels.Distance.COSINE,
            ),
        )
        logger.info(f"创建 collection: {collection_name}")

    # Create the Qdrant store once, outside the loop
    store = Qdrant(
        client=qdrant_client,
        collection_name=collection_name,
        embeddings=embeddings,
    )

    success_urls = []
    failed_urls = []
    total_chunks = 0

    # 逐个处理 URL
    for url in urls:
        try:
            logger.info(f"处理 URL: {url}")

            # 1. 加载 HTML 内容
            docs = load_html(url)

            # 2. 分割文档为文本块
            chunks = text_splitter.split_documents(docs)
            logger.info(f"分割成 {len(chunks)} 个文本块")

            # 3. 存入 Qdrant（追加模式）
            if chunks:
                store.add_documents(chunks)
                total_chunks += len(chunks)
                success_urls.append(url)
                logger.info(f"成功添加 {len(chunks)} 个文本块")
            else:
                logger.warning(f"URL {url} 没有生成任何文本块")
                success_urls.append(url)

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"处理 URL {url} 失败: {error_msg}")
            failed_urls.append({"url": url, "error": error_msg})

    result = {
        "success": success_urls,
        "failed": failed_urls,
        "total_chunks": total_chunks,
    }

    logger.info(f"处理完成: 成功 {len(success_urls)}, 失败 {len(failed_urls)}, 总文本块 {total_chunks}")
    return result


def baidu_search(query: str, api_key: str) -> str:
    """调用百度AI搜索API，返回AI总结和搜索结果。"""
    url = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": query}],
        "model": "ernie-4.5-turbo-128k",
        "stream": False,
        "search_source": "baidu_search_v2"
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30, proxies={"http": None, "https": None})
    response.raise_for_status()
    data = response.json()

    answer = data["choices"][0]["message"]["content"]
    refs = data.get("references", [])
    ref_text = "\n".join([f"- {r['title']}: {r.get('content', '')[:100]}" for r in refs])
    return f"AI总结: {answer}\n\n搜索结果:\n{ref_text}"

@tool
def search_tool(query: str) -> str:
    """百度搜索工具，用于搜索未知信息或实时资讯。输入搜索关键词，返回AI总结和搜索结果摘要。"""
    try:
        return baidu_search(query, BAIDU_AI_SEARCH_API_KEY)
    except Exception as e:
        return f"搜索失败: {str(e)[:100]}"

@tool
def get_info_from_local_db(query:str):
    "查询本地知识库，用于回答2026年或者马年运势相关问题"
    retriever = _get_retriever(file_name=QDRANT_COLLECTION)
    result = retriever.invoke(query)
    return result

@tool
def bazi_cesuan(query:str, api_key: str = None):
    """只有做八字排盘的时候才会使用这个工具,需要输入用户姓名和出生年月日时，如果缺少用户姓名和出生年月日时则不可用."""
    if api_key is None:
        api_key = YUANFENJU_API_KEY
    url = "https://api.yuanfenju.com/index.php/v1/Bazi/cesuan"
    prompt = ChatPromptTemplate.from_template(
        """你是一个参数查询助手，根据用户输入内容找出相关的参数并按json格式返回。JSON字段如下： -"api_key":"6Ahpd9A7AN6xfdKmV4bVU0Jqm", - "name":"姓名", - "sex":"性别，0表示男，1表示女，根据姓名判断", - "type":"日历类型，0农历，1公里，默认1"，- "year":"出生年份 例：1998", - "month":"出生月份 例 8", - "day":"出生日期，例：8", - "hours":"出生小时 例 14", - "minute":"0", - "province":"省份，默认北京市", - "city":"城市，默认北京市"，如果没有找到相关参数，则需要提醒用户告诉你这些内容，只返回数据结构，不要有其他的评论，用户输入:{query}"""
    )
    parser = JsonOutputParser()
    prompt = prompt.partial(format_instructions=parser.get_format_instructions())
    chain = prompt | ChatOpenAI(
        model=LLM_MODEL_NAME,
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=0
    ) | parser
    data = chain.invoke({"query":query})

    # 默认出生地为北京
    if 'province' not in data or not data['province']:
        data['province'] = '北京市'
    if 'city' not in data or not data['city']:
        data['city'] = '北京市'

    # 使用 form-urlencoded 格式发送 POST 请求
    result = requests.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if result.status_code == 200:
        try:
            json_data = result.json()
            # 缘份居 API 返回格式
            if json_data.get("errcode") == 0:
                bazi = json_data.get("data", {}).get("bazi_info", {}).get("bazi", "")
                if bazi:
                    return f"八字为: {bazi}"
                else:
                    # 检查错误信息
                    errmsg = json_data.get("errmsg", "")
                    return f"八字查询失败: {errmsg}"
            else:
                return f"八字查询失败: {json_data.get('errmsg', '未知错误')}"
        except Exception as e:
            return f"八字查询失败: {str(e)[:100]}"
    else:
        return "技术错误，请告诉用户稍后再试。"

@tool
def yaoyigua() -> str:
    """
    摇卦工具，用于占卜抽签。
    只有用户想要占卜抽签的时候才会使用这个工具。
    """
    url = "https://api.yuanfenju.com/index.php/v1/Zhanbu/yaogua"
    data = {"api_key": YUANFENJU_API_KEY}

    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("errcode") == 0:
                gua_info = result.get("data", {}).get("gua", {})
                gua_name = gua_info.get("name", "")
                gua_desc = gua_info.get("description", "")
                return f"摇卦结果: {gua_name} - {gua_desc}"
            else:
                return f"摇卦失败: {result.get('errmsg', '未知错误')}"
        else:
            return f"摇卦失败，状态码: {response.status_code}"
    except Exception as e:
        return f"摇卦异常: {str(e)[:100]}"
    
@tool
def jiemeng(query:str) -> str:
    """只有用户想要解梦的时候才会使用这个工具,需要输入用户梦境的内容，如果缺少用户梦境的内容则不可用。"""
    api_key = YUANFENJU_API_KEY
    url = "https://api.yuanfenju.com/index.php/v1/Gongju/zhougong"

    # 提取关键词
    prompt = ChatPromptTemplate.from_template("根据内容提取1个关键词，只返回关键词，内容为:{topic}")
    chain = prompt | ChatOpenAI(
        model=LLM_MODEL_NAME,
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=0
    ) | StrOutputParser()
    keyword = chain.invoke({"topic": query}).strip()
    logger.debug(f"[jiemeng] 提取关键词: {keyword}")

    # 调用解梦 API
    result = requests.post(url, data={"api_key": api_key, "title_zhougong": keyword}, timeout=10)
    logger.debug(f"[jiemeng] 状态码: {result.status_code}, 返回: {result.text[:300]}")

    if result.status_code == 200:
        try:
            data = result.json()
            if data.get("errcode") == 0:
                dream_info = data.get("data", {})
                title = dream_info.get("title", "")
                content = dream_info.get("content", "")
                if title or content:
                    return f"周公解梦: {title} - {content}"
                else:
                    return f"未找到'{keyword}'相关的解梦内容。"
            else:
                errmsg = data.get('errmsg', '未知错误')
                if "无权" in errmsg or "会员" in errmsg or "关键词" in errmsg:
                    return "解梦功能需要会员权限，暂时无法使用。"
                return f"解梦失败: {errmsg}"
        except Exception as e:
            return f"解梦解析失败: {str(e)[:100]}"
    else:
        return f"解梦失败，状态码: {result.status_code}"


# ==========================================
# Voice Output (Qwen3-TTS)
# ==========================================

# 将长文本按句子边界切分为不超过 max_len 的片段
def _split_text_for_tts(text: str, max_len: int = 500) -> list[str]:
    """将长文本按句子边界切分为不超过 max_len 的片段"""
    import re
    if len(text) <= max_len:
        return [text]
    # 按句号、感叹号、问号、换行切分
    sentences = re.split(r'([。！？\n])', text)
    chunks, current = [], ""
    for i in range(0, len(sentences) - 1, 2):
        sentence = sentences[i] + sentences[i + 1]
        if len(current) + len(sentence) > max_len:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current += sentence
    # 处理最后可能没有标点的部分
    remainder = sentences[-1] if len(sentences) % 2 else ""
    if current:
        current += remainder
        chunks.append(current)
    elif remainder:
        chunks.append(remainder)
    return chunks


# 调用一次 Qwen3-TTS API，返回音频 bytes
def _call_tts(text: str, voice: str, instruction: str | None) -> bytes | None:
    """调用一次 Qwen3-TTS API，返回音频 bytes"""
    import dashscope
    params = {
        "model": TTS_MODEL,
        "api_key": DASHSCOPE_API_KEY,
        "text": text,
        "voice": voice,
        "language_type": "Chinese",
        "stream": False,
    }
    if instruction:
        params["instructions"] = instruction
        params["optimize_instructions"] = True

    response = dashscope.MultiModalConversation.call(**params)
    if response.status_code == 200:
        audio_url = response.output.audio.url
        if audio_url:
            audio_resp = requests.get(audio_url, timeout=60)
            if audio_resp.status_code == 200:
                return audio_resp.content
            else:
                logger.error(f"下载音频失败: HTTP {audio_resp.status_code}")
        else:
            logger.error("TTS 响应中没有 audio URL")
    else:
        logger.error(f"TTS API 错误: {response.code} - {response.message}")
    return None


# 生成语音音频（Qwen3-TTS），长文本自动分段合成后拼接
async def get_voice(text: str, mood: str, voice: str = TTS_VOICE) -> bytes:
    """
    Generate voice audio using Qwen3-TTS.
    长文本自动按句子边界切分，分段合成后拼接。

    Args:
        text: Text to convert to speech
        mood: Mood from Agent (default/upbeat/angry/depressed/friendly/cheerful)
        voice: Voice ID for Qwen3-TTS, default "Eldric Sage"

    Returns:
        audio bytes (WAV format)
    """
    from pydub import AudioSegment
    import io

    # # 禁用代理
    # for key in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    #     os.environ.pop(key, None)

    # 获取情绪对应的 TTS 指令
    instruction = MOOD_TO_INSTRUCTION.get(mood)
    logger.info(f"生成语音: mood={mood}, text_len={len(text)}")

    # 切分文本
    # 切分文本，每段不超过 500 字符
    chunks = _split_text_for_tts(text)
    logger.info(f"文本切分为 {len(chunks)} 段")

    # 逐段调用 TTS API 合成音频
    audio_segments = []
    for i, chunk in enumerate(chunks):
        logger.info(f"合成第 {i+1}/{len(chunks)} 段: {chunk[:30]}...")
        audio_bytes = _call_tts(chunk, voice, instruction)
        if audio_bytes is None:
            logger.error(f"第 {i+1} 段合成失败，跳过")
            continue
        audio_segments.append(AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav"))

    if not audio_segments:
        logger.error("所有段落都合成失败")
        return None

    # 拼接所有音频片段
    combined = audio_segments[0]
    for seg in audio_segments[1:]:
        combined += seg

    # 导出为 WAV 格式的 bytes
    output = io.BytesIO()
    combined.export(output, format="wav")
    result = output.getvalue()
    logger.info(f"语音合成完成: {len(result)} bytes")
    return result


if __name__ == "__main__":
    print("测试: 八字测算")
    print("=" * 50)
    try:
        result = bazi_cesuan("陈铭明 1987年7月4日出生")
        print(result)
    except Exception as e:
        print(f"八字测算失败: {e}")

    print("\n" + "=" * 50)
    print("测试 2: 本地知识库检索")
    print("=" * 50)
    try:
        db_result = get_info_from_local_db.invoke("龙年运势")
        print(f"找到 {len(db_result)} 条结果")
        for i, doc in enumerate(db_result):
            print(f"\n--- 结果 {i+1} ---")
            print(doc.page_content[:300])
    except Exception as e:
        print(f"本地知识库搜索失败: {e}")