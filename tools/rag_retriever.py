"""
RAG 检索工具
============

作用：接收用户问题，在 Qdrant 向量库里找最相关的知识片段，返回给 LLM。

流程：
  用户问题 → Embedding（转成向量）→ Qdrant 相似度搜索 → 返回最相关的文本片段

Java 类比：
  这相当于一个 DAO 层，只不过查询方式不是 SELECT WHERE，
  而是"找出和这段文字语义最相似的记录"。
"""

from qdrant_client import QdrantClient
from fastembed import TextEmbedding
from langchain_core.tools import tool

# ── 配置（必须和 ingest.py 保持一致）────────────────────────
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "travel_knowledge"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
TOP_K = 3  # 返回最相关的前3条结果

# ── 初始化（模块加载时执行一次）────────────────────────────
_client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
_model = TextEmbedding(EMBEDDING_MODEL)


@tool
def retrieve_local_knowledge(query: str) -> str:
    """
    从本地知识库中检索与旅行相关的信息。
    当用户询问景点介绍、美食推荐、旅游攻略、门票价格、交通方式等本地知识时，优先调用此工具。
    参数 query：用户的查询内容，如"成都有什么好吃的"、"北京故宫门票多少钱"
    """
    try:
        # 1. 把用户问题转成向量
        query_vector = list(_model.embed([query]))[0].tolist()

        # 2. 在 Qdrant 里搜索最相似的文本块
        response = _client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=TOP_K,
            score_threshold=0.3,  # 相似度低于0.3的结果不返回（避免不相关内容）
        )
        results = response.points
    except Exception as exc:
        return (
            "本地知识库暂时不可用，建议改用联网搜索补充信息。"
            f"（检索异常：{exc}）"
        )

    if not results:
        return "本地知识库中没有找到相关信息，建议联网搜索。"

    # 3. 整理结果，返回给 LLM
    output = "【本地知识库检索结果】\n\n"
    for i, result in enumerate(results, 1):
        source = result.payload.get("source", "未知来源")
        text = result.payload.get("text", "")
        score = result.score
        output += f"[{i}] 来源：{source}（相关度：{score:.2f}）\n"
        output += f"{text}\n\n"

    return output.strip()
