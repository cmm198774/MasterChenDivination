# RAG 数据库数据添加功能设计

## 概述

实现 RAG 数据库的数据添加功能，支持从本地 HTML 文件和远程 URL 加载内容，分割后存入 Qdrant 向量数据库。

## 需求

1. **输入支持**
   - 本地 HTML 文件路径
   - 远程 URL（http/https）
   - 支持批量处理多个 URL

2. **数据处理**
   - 使用 RecursiveCharacterTextSplitter 分割文档
   - chunk_size: 1000
   - chunk_overlap: 100

3. **存储**
   - Embedding 模型: text-embedding-v3 (DashScopeEmbeddings)
   - 存储位置: local_qdrand
   - Collection 名称: yunshi_2026
   - 模式: 追加（不清空现有数据）

4. **集成**
   - 先实现独立测试脚本
   - 验证查询功能正常
   - 集成到 server.py 的 add_urls() 接口

## 架构设计

```
用户请求 (URL 列表)
  ↓
add_urls_to_db(urls, collection_name)
  ↓
循环处理每个 URL
  ↓
load_html(source) - 判断本地/远程
  ├─ 本地文件 → BSHTMLLoader
  └─ 远程 URL → WebBaseLoader
  ↓
RecursiveCharacterTextSplitter 分割
  ↓
DashScopeEmbeddings (text-embedding-v3) 编码
  ↓
Qdrant.from_documents() 追加到 collection
```

## 核心组件

### 1. load_html(source: str) -> List[Document]

辅助函数，根据输入类型选择合适的 Loader。

**参数:**
- source: HTML 文件路径或 URL

**返回:**
- 文档列表

**逻辑:**
```python
def load_html(source: str) -> List[Document]:
    if source.startswith("http://") or source.startswith("https://"):
        # 远程 URL
        from langchain_community.document_loaders import WebBaseLoader
        loader = WebBaseLoader(source)
    else:
        # 本地文件
        from langchain_community.document_loaders import BSHTMLLoader
        loader = BSHTMLLoader(source)
    return loader.load()
```

### 2. add_urls_to_db(urls: List[str], collection_name: str = "yunshi_2026")

主函数，处理 URL 列表并添加到数据库。

**参数:**
- urls: URL 列表（可以是本地路径或远程 URL）
- collection_name: Qdrant collection 名称，默认 "yunshi_2026"

**返回:**
- dict: 包含成功/失败信息的字典

**逻辑:**
1. 初始化 QdrantClient 和 Embedding
2. 循环处理每个 URL
3. 加载 HTML 文档
4. 使用 RecursiveCharacterTextSplitter 分割
5. 编码并追加到 Qdrant
6. 返回处理结果统计

### 3. server.py 集成

```python
@app.post("/add_urls")
def add_urls(urls: List[str]):
    result = add_urls_to_db(urls, collection_name="yunshi_2026")
    return result
```

## 测试计划

### 阶段 1: 独立测试脚本

创建 `test_scripts/test_add_urls.py`:

1. 加载本地 HTML 文件
   - 测试文件: `html/八字未来运势_免费八字未来预测_四柱八字流年运势_未来趋势解析-缘份居.html`
2. 验证数据已添加到 Qdrant
3. 使用 get_info_from_local_db 查询验证

### 阶段 2: 集成测试

1. 启动 FastAPI 服务器
2. POST 请求到 /add_urls
3. 验证返回结果
4. 查询验证数据可用

## 错误处理

1. **文件/URL 不存在**
   - 记录错误日志
   - 继续处理其他 URL
   - 返回失败列表

2. **HTML 解析失败**
   - 捕获异常
   - 记录日志
   - 跳过该文件

3. **Embedding 调用失败**
   - 捕获异常
   - 记录日志
   - 返回错误信息

## 依赖

```python
from langchain_community.document_loaders import BSHTMLLoader, WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Qdrant
from langchain_community.embeddings import DashScopeEmbeddings
from qdrant_client import QdrantClient
```

## 配置参数

```python
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100
COLLECTION_NAME = "yunshi_2026"
EMBEDDING_MODEL = "text-embedding-v3"
QDRANT_BASE_DIR = "local_qdrand"
```
