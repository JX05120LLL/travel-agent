from fastembed import TextEmbedding

model = TextEmbedding("BAAI/bge-small-zh-v1.5")

# 把三段文字都转成向量
texts = ["成都火锅", "成都麻辣烫", "北京故宫"]
vectors = list(model.embed(texts))

# 看看向量长什么样
print("向量维度：", len(vectors[0]))
print("前5个数字：", vectors[0][:5])
