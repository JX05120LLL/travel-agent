r"""
FastAPI Web 应用
================

运行方法：
  cd d:\code\python-workspace\travel-agent
  venv\Scripts\activate
  python web/app.py
  然后打开 http://localhost:7860
"""

import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage, HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

sys.path.insert(0, str(PROJECT_ROOT))

app = FastAPI(title="旅行规划助手")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

_agent = None


def get_agent():
    """懒加载 Agent，避免页面首开时阻塞太久。"""
    global _agent
    if _agent is None:
        from agent.graph import agent as compiled_agent
        _agent = compiled_agent
    return _agent


def format_sse(event: str, payload: dict) -> str:
    """把事件编码成标准 SSE 格式。"""
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def extract_text(message_chunk) -> str:
    """统一提取 LangGraph stream chunk 里的文本。"""
    raw = getattr(message_chunk, "content", "") or ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(getattr(block, "text", "") or str(block) for block in raw)
    return str(raw)


def build_history_messages(history_raw: str) -> list:
    """把前端传来的历史消息 JSON 转回 LangChain 消息对象。"""
    if not history_raw:
        return []

    try:
        items = json.loads(history_raw)
    except json.JSONDecodeError:
        return []

    messages = []
    for item in items:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if not content:
            continue

        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    return messages


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """渲染首页。"""
    suggestion_prompts = [
        "帮我规划从西安出发，3天成都旅行",
        "北京周末两天亲子游怎么安排",
        "成都今天适合去哪些室内景点",
        "把一份杭州美食路线整理成清单",
    ]
    return templates.TemplateResponse(
        name="index.html",
        request=request,
        context={"suggestion_prompts": suggestion_prompts},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """避免浏览器默认请求 favicon 时出现 404 噪音。"""
    return Response(status_code=204)


@app.post("/chat")
async def chat(message: str = Form(...), history: str = Form("[]")):
    """接收消息并返回标准 SSE 流。"""
    user_input = message.strip()
    if not user_input:
        return StreamingResponse(
            iter([format_sse("error", {"message": "消息不能为空"})]),
            media_type="text/event-stream",
        )

    prior_messages = build_history_messages(history)

    def event_stream():
        agent = get_agent()
        input_messages = prior_messages + [HumanMessage(content=user_input)]
        input_data = {"messages": input_messages}
        has_tool_output = False
        has_answer_token = False

        yield format_sse("phase", {"value": "planning", "label": "正在分析你的需求"})

        try:
            for event in agent.stream(input_data, stream_mode="messages"):
                if not isinstance(event, tuple) or len(event) != 2:
                    continue

                message_chunk, metadata = event
                node = metadata.get("langgraph_node", "")
                text = extract_text(message_chunk)

                if node == "tools":
                    if not has_tool_output:
                        has_tool_output = True
                        yield format_sse(
                            "phase",
                            {"value": "tooling", "label": "正在调用旅行工具"},
                        )
                    if text:
                        yield format_sse("tool", {"content": text})

                elif node == "llm_node" and text:
                    if not has_answer_token:
                        has_answer_token = True
                        yield format_sse(
                            "phase",
                            {"value": "answering", "label": "正在整理最终建议"},
                        )
                    yield format_sse("token", {"content": text})

            yield format_sse("done", {"status": "ok"})
        except Exception as exc:
            yield format_sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    print("旅行规划助手已启动：http://localhost:7860")
    uvicorn.run("web.app:app", host="0.0.0.0", port=7860, reload=False)
