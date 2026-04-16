"""
企业微信（WeChat Work）Webhook 推送工具
=======================================

作用：当 Agent 识别到用户说"发到企业微信"时，把旅行规划内容推送到企业微信群。

企业微信机器人 Webhook 文档：
https://developer.work.weixin.qq.com/document/path/91770

Java 类比：同上，飞书工具的企业微信版本。
"""

import os
import requests
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# ── 配置 ────────────────────────────────────────────────────────
WECHAT_WORK_WEBHOOK = os.getenv("WECHAT_WORK_WEBHOOK_URL")
WECHAT_WORK_APP_NAME = "旅行规划助手"


@tool
def send_to_wechat_work(message: str) -> str:
    """
    把旅行规划内容发送到企业微信群。

    当用户说"发到企业微信"、"推送企微"、"发企微"时调用此工具。

    参数 message：推送到企业微信的内容（如行程规划、景点推荐等）
    返回：发送结果
    """
    if not WECHAT_WORK_WEBHOOK:
        return "❌ 企业微信 Webhook 未配置。请在 .env 文件中设置 WECHAT_WORK_WEBHOOK_URL"

    payload = {
        "msgtype": "text",
        "text": {
            "content": f"📍 **{WECHAT_WORK_APP_NAME}**\n\n{message}\n\n---\n由 AI 自动生成，如有问题请联系管理员"
        }
    }

    try:
        response = requests.post(WECHAT_WORK_WEBHOOK, json=payload, timeout=10)
        result = response.json()

        if response.status_code == 200 and result.get("errcode") == 0:
            return f"✅ 已成功发送到企业微信！"
        else:
            error_msg = result.get("errmsg", "未知错误")
            return f"❌ 企业微信发送失败：{error_msg}"
    except requests.exceptions.RequestException as e:
        return f"❌ 网络错误，发送到企业微信失败：{str(e)}"
