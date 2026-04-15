from openai import OpenAI
from dotenv import load_dotenv
import os

# 读取 .env 文件里的 API Key
load_dotenv()

# 创建客户端，指向 DeepSeek 的服务器
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 多轮对话的消息列表（每次对话都把历史记录带上）
messages = [
    {"role": "system", "content": "你是一个专业的旅行规划助手，帮助用户规划旅行行程。"}
]

print("旅行助手已启动，输入 quit 退出\n")

while True:
    user_input = input("你：")
    if user_input.lower() == "quit":
        break

    # 把用户的话加入历史
    messages.append({"role": "user", "content": user_input})

    # 调用 DeepSeek API
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages
    )

    # 取出回复内容
    reply = response.choices[0].message.content

    # 把 AI 的回复也加入历史（这样下一轮它能记住上文）
    messages.append({"role": "assistant", "content": reply})

    print(f"\n助手：{reply}\n")
