"""
飞书（Feishu/Lark）Webhook 推送工具
===================================

作用：当 Agent 识别到用户说"发到飞书"时，把旅行规划内容推送到飞书群。

飞书机器人 Webhook 文档：
https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN

Java 类比：这是一个 HttpClient 调第三方 Webhook API，
相当于 Java 里用 RestTemplate 或 OkHttp 发 HTTP POST。
"""

import os
import requests
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# ── 配置 ────────────────────────────────────────────────────────
# 飞书 Webhook 地址（在飞书群机器人设置里复制）
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK_URL")
FEISHU_APP_NAME = "旅行规划助手"  # 机器人名字


@tool
def send_to_feishu(message: str) -> str:
    """
    把旅行规划内容发送到飞书群。

    当用户说"发到飞书"、"推送飞书"、"发飞书"时调用此工具。

    参数 message：推送到飞书的内容（如行程规划、景点推荐等）
    返回：发送结果
    """
    if not FEISHU_WEBHOOK:
        return "❌ 飞书 Webhook 未配置。请在 .env 文件中设置 FEISHU_WEBHOOK_URL"

    payload = {
        "msg_type": "text",
        "content": {
            "text": f"📍 **{FEISHU_APP_NAME}**\n\n{message}\n\n---\n由 AI 自动生成，如有问题请联系管理员"
        }
    }

    try:
        response = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        result = response.json()

        if response.status_code == 200 and result.get("code") == 0:
            return f"✅ 已成功发送到飞书！"
        else:
            error_msg = result.get("msg", "未知错误")
            return f"❌ 飞书发送失败：{error_msg}"
    except requests.exceptions.RequestException as e:
        return f"❌ 网络错误，发送到飞书失败：{str(e)}"
