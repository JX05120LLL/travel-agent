"""
RAG 知识库入库脚本
==================

作用：把 rag/data/ 下的 md 文档向量化，存入 Qdrant。
只需运行一次（或文档更新时重新运行）。

流程：
  读取 md 文件 → 按段落切分 → Embedding（转成向量） → 存入 Qdrant

使用 fastembed 替代 sentence-transformers：
  - 不依赖 PyTorch，安装轻量
  - 使用 ONNX 运行模型，速度快
  - 模型：BAAI/bge-small-zh-v1.5（专为中文优化，512维）

运行方法：
  venv\\Scripts\\activate
  python rag/ingest.py
"""

import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding

# ── 配置 ─────────────────────────────────────────────────────
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "travel_knowledge"   # Qdrant 里的"表名"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"  # 中文 Embedding 模型（fastembed 内置支持）
VECTOR_DIM = 512   # bge-small-zh-v1.5 的向量维度
CHUNK_SIZE = 300   # 每个文本块最大字符数

# ── 初始化 ───────────────────────────────────────────────────
print("正在加载 Embedding 模型（首次运行会自动下载，约130MB）...")
model = TextEmbedding(EMBEDDING_MODEL)
print(f"模型加载完成，向量维度：{VECTOR_DIM}")

client = QdrantClient(url=QDRANT_URL)


def split_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    按段落切分文本。

    为什么要切分？
    因为 Embedding 模型有输入长度限制，而且短段落的语义更精准，
    检索时能更准确地找到相关内容。

    切分策略：
    1. 先按双换行（段落）切分
    2. 如果某段太长，再按句子切分
    """
    chunks = []
    # 先按段落（双换行）切分
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            # 段落太长，按句号/换行继续切
            sentences = para.replace("。", "。\n").replace("\n", "\n").split("\n")
            current = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current) + len(sent) <= chunk_size:
                    current += sent
                else:
                    if current:
                        chunks.append(current)
                    current = sent
            if current:
                chunks.append(current)

    return [c for c in chunks if len(c) > 10]  # 过滤掉太短的片段


def load_documents(data_dir: str) -> list[dict]:
    """
    读取 data/ 目录下所有 md 文件，切分成文本块。

    返回格式：
    [
        {"text": "...", "source": "成都美食.md"},
        ...
    ]
    """
    documents = []
    md_files = glob.glob(os.path.join(data_dir, "*.md"))

    if not md_files:
        print(f"警告：{data_dir} 下没有找到 md 文件")
        return []

    for filepath in md_files:
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = split_text(content)
        for chunk in chunks:
            documents.append({
                "text": chunk,
                "source": filename,
            })
        print(f"  {filename}：切分成 {len(chunks)} 个文本块")

    return documents


def create_collection():
    """
    在 Qdrant 中创建 collection（相当于创建数据库表）。
    如果已存在则删除重建（重新入库时用）。
    """
    # 检查是否已存在
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"collection '{COLLECTION_NAME}' 已存在，删除重建...")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_DIM,      # 向量维度，必须和 Embedding 模型一致
            distance=Distance.COSINE,  # 相似度计算方式：余弦相似度
        ),
    )
    print(f"collection '{COLLECTION_NAME}' 创建成功")


def ingest():
    """主入库流程"""
    # 1. 找到 data 目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    # 2. 读取并切分文档
    print(f"\n读取文档：{data_dir}")
    documents = load_documents(data_dir)
    if not documents:
        return
    print(f"共 {len(documents)} 个文本块")

    # 3. 创建 Qdrant collection
    print(f"\n创建 Qdrant collection...")
    create_collection()

    # 4. Embedding + 存入 Qdrant
    print(f"\n开始向量化并写入 Qdrant...")
    texts = [doc["text"] for doc in documents]

    # 批量 Embedding（比一条条处理快很多）
    # fastembed 返回生成器，用 list() 转成列表
    print("  正在计算向量（请稍候）...")
    vectors = list(model.embed(texts))

    # 构造 Qdrant 的数据格式
    points = [
        PointStruct(
            id=i,
            vector=vectors[i].tolist(),
            payload={
                "text": documents[i]["text"],     # 原始文本（检索后返回给 LLM）
                "source": documents[i]["source"],  # 来源文件名
            },
        )
        for i in range(len(documents))
    ]

    # 批量写入
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"\n✓ 入库完成！共写入 {len(points)} 条向量数据")
    print(f"  可在 http://localhost:6333/dashboard 查看")


if __name__ == "__main__":
    ingest()
