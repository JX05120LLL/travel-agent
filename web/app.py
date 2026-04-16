r"""
Flask 后端 - 仅提供 /chat API 接口
==================================

运行方法：
  cd d:\code\python-workspace\travel-agent
  venv\Scripts\activate
  python web/app.py
  然后打开 http://localhost:7860
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, Response, send_from_directory

app = Flask(__name__)

# ── Agent 懒加载 ────────────────────────────────────────────────
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        from agent.graph import agent as _ag
        _agent = _ag
    return _agent


# ── SSE 流式接口 ────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    """POST: 发送消息，返回 SSE 流式响应"""
    user_input = request.form.get("message", "").strip()
    if not user_input:
        return "no message", 400

    def generate():
        agent = get_agent()
        input_data = {"messages": [("user", user_input)]}
        in_tool_phase = False

        for event in agent.stream(input_data, stream_mode="messages"):
            if not isinstance(event, tuple) or len(event) != 2:
                continue

            msg_chunk, metadata = event
            node = metadata.get("langgraph_node", "")

            # 提取纯文本
            raw = getattr(msg_chunk, "content", "") or ""
            if isinstance(raw, str):
                text = raw
            elif isinstance(raw, list):
                text = "".join(
                    getattr(b, "text", "") or str(b) for b in raw
                )
            else:
                text = str(raw)

            if node == "tools":
                if not in_tool_phase:
                    in_tool_phase = True
                    yield "data: TOOL_CALL\n\n"
                if text:
                    yield f"data: TOOL_RESULT:{text}\n\n"

            elif node == "llm_node":
                in_tool_phase = False
                if text:
                    yield f"data: TEXT:{text}\n\n"

        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 静态文件 ────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    print("旅行规划助手已启动：http://localhost:7860")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
