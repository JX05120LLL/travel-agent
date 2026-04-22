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
import uuid
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

sys.path.insert(0, str(PROJECT_ROOT))

from db.models import User
from db.session import get_db
from services.amap_service import AmapService
from services.comparison_service import ComparisonService
from services.errors import (
    ServiceConfigError,
    ServiceIntegrationError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from services.message_service import MessageService
from services.memory_service import MemoryService
from services.plan_option_service import PlanOptionBranchView, PlanOptionService
from services.session_management_service import SessionManagementService
from services.session_service import SessionService
from services.session_workspace_service import SessionWorkspaceService
from services.trip_service import TripService
from web.auth import get_current_user

app = FastAPI(title="旅行规划助手")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

_agent = None
# 统一当前用户依赖，后续接真实认证时优先只改这一层。
CurrentUserDep = Annotated[User, Depends(get_current_user)]


class SessionSummaryResponse(BaseModel):
    """会话列表响应。"""

    id: str
    title: str
    status: str
    summary: str | None
    latest_user_message: str | None
    created_at: str
    updated_at: str
    last_message_at: str


class SessionRenameRequest(BaseModel):
    """重命名会话请求。"""

    title: str


class MessageResponse(BaseModel):
    """消息列表响应。"""

    id: str
    role: str
    content: str
    content_format: str
    sequence_no: int
    created_at: str
    metadata: dict


class SessionMessagesResponse(BaseModel):
    """会话详情与消息列表。"""

    session_id: str
    title: str
    status: str
    messages: list[MessageResponse]


class SessionMemoryMessageResponse(BaseModel):
    """会话记忆视图里的最近消息。"""

    id: str
    role: str
    content_preview: str
    plan_option_id: str | None
    created_at: str


class SessionMemoryResponse(BaseModel):
    """会话与记忆管理快照。"""

    session_id: str
    title: str
    status: str
    summary: str | None
    active_plan_option_id: str | None
    active_plan_title: str | None
    active_plan_summary: str | None
    active_comparison_summary: str | None
    user_preference_summary: str | None
    recent_messages: list[SessionMemoryMessageResponse]
    plan_options: list["PlanOptionSummaryResponse"]


class UserPreferenceResponse(BaseModel):
    """用户长期偏好响应。"""

    id: str
    category: str
    key: str
    value: dict
    source: str
    confidence: str
    updated_at: str


class SessionEventResponse(BaseModel):
    """会话事件审计响应。"""

    id: str
    event_type: str
    message_id: str | None
    plan_option_id: str | None
    comparison_id: str | None
    trip_id: str | None
    event_payload: dict
    created_at: str


class HistoryRecallLogResponse(BaseModel):
    """历史召回日志响应。"""

    id: str
    recall_type: str
    matched_record_type: str | None
    matched_record_id: str | None
    matched_count: int
    confidence: str | None
    summary: str | None
    decision_summary: str | None
    created_at: str


class CheckpointCreateRequest(BaseModel):
    """创建检查点请求。"""

    label: str | None = None


class SessionCheckpointResponse(BaseModel):
    """会话检查点响应。"""

    id: str
    label: str
    active_plan_option_id: str | None
    active_comparison_id: str | None
    snapshot_scope: dict | None
    summary_restore_mode: str | None
    created_at: str


class PlanComparisonCreateRequest(BaseModel):
    """创建或更新方案比较请求。"""

    name: str | None = None
    plan_option_ids: list[str]


class PlanComparisonSummaryResponse(BaseModel):
    """方案比较摘要响应。"""

    id: str
    name: str
    status: str
    summary: str | None
    recommended_option_id: str | None
    comparison_dimensions: list
    updated_at: str


class SessionComparisonsResponse(BaseModel):
    """当前会话的方案比较列表。"""

    session_id: str
    active_comparison_id: str | None
    items: list["PlanComparisonSummaryResponse"]


class TripCreateRequest(BaseModel):
    """创建正式行程请求。"""

    plan_option_id: str | None = None
    comparison_id: str | None = None


class TripSummaryResponse(BaseModel):
    """正式行程摘要响应。"""

    id: str
    title: str
    status: str
    source_plan_option_id: str | None
    primary_destination: str | None
    total_days: int | None
    summary: str | None
    selected_from_comparison_id: str | None
    confirmed_at: str | None
    updated_at: str


class SessionTripsResponse(BaseModel):
    """当前会话的正式行程列表。"""

    session_id: str
    items: list["TripSummaryResponse"]


class TripDetailResponse(BaseModel):
    """正式行程详情响应。"""

    id: str
    title: str
    status: str
    source_plan_option_id: str | None
    primary_destination: str | None
    total_days: int | None
    summary: str | None
    plan_markdown: str | None
    selected_from_comparison_id: str | None
    destinations: list[dict]
    itinerary_days: list[dict]
    confirmed_at: str | None
    updated_at: str


class PlanOptionCreateRequest(BaseModel):
    """创建候选方案请求。"""

    title: str | None = None
    primary_destination: str | None = None
    travel_start_date: str | None = None
    travel_end_date: str | None = None
    total_days: int | None = None
    summary: str | None = None
    plan_markdown: str | None = None
    activate: bool = True


class PlanOptionSummaryResponse(BaseModel):
    """候选方案摘要响应。"""

    id: str
    title: str
    status: str
    branch_name: str | None
    parent_plan_option_id: str | None
    branch_root_option_id: str
    source_plan_option_id: str | None
    branch_depth: int
    child_count: int
    version_no: int
    primary_destination: str | None
    total_days: int | None
    summary: str | None
    is_selected: bool
    updated_at: str


class SessionPlanOptionsResponse(BaseModel):
    """当前会话的候选方案列表。"""

    session_id: str
    active_plan_option_id: str | None
    items: list[PlanOptionSummaryResponse]


class PlanOptionSaveResultResponse(BaseModel):
    """保存候选方案后的结果。"""

    created_count: int
    message: str
    items: list[PlanOptionSummaryResponse]


SessionMemoryResponse.model_rebuild()
SessionComparisonsResponse.model_rebuild()
SessionTripsResponse.model_rebuild()


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


def serialize_session(session) -> SessionSummaryResponse:
    """把 ORM 会话对象转换成接口响应。"""
    return SessionSummaryResponse(
        id=str(session.id),
        title=session.title,
        status=session.status,
        summary=session.summary,
        latest_user_message=session.latest_user_message,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        last_message_at=session.last_message_at.isoformat(),
    )


def serialize_message(message) -> MessageResponse:
    """把 ORM 消息对象转换成接口响应。"""
    return MessageResponse(
        id=str(message.id),
        role=message.role,
        content=message.content,
        content_format=message.content_format,
        sequence_no=message.sequence_no,
        created_at=message.created_at.isoformat(),
        metadata=message.message_metadata or {},
    )


def parse_optional_date(value: str | None):
    """把 YYYY-MM-DD 字符串转成 date。"""
    if not value:
        return None
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d").date()


def _raise_http_for_integration_error(exc: Exception) -> None:
    """统一映射第三方集成错误到 HTTP 状态码。"""
    if isinstance(exc, ServiceValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ServiceConfigError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(exc, ServiceIntegrationError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="高德服务调用失败") from exc


def serialize_plan_option(plan_option_view: PlanOptionBranchView) -> PlanOptionSummaryResponse:
    """把 ORM 候选方案对象转换成接口响应。"""
    plan_option = plan_option_view.plan_option
    return PlanOptionSummaryResponse(
        id=str(plan_option.id),
        title=plan_option.title,
        status=plan_option.status,
        branch_name=plan_option.branch_name,
        parent_plan_option_id=(
            str(plan_option.parent_plan_option_id) if plan_option.parent_plan_option_id else None
        ),
        branch_root_option_id=str(plan_option_view.branch_root_id),
        source_plan_option_id=(
            str(plan_option.source_plan_option_id) if plan_option.source_plan_option_id else None
        ),
        branch_depth=plan_option_view.branch_depth,
        child_count=plan_option_view.child_count,
        version_no=plan_option.version_no,
        primary_destination=plan_option.primary_destination,
        total_days=plan_option.total_days,
        summary=plan_option.summary,
        is_selected=plan_option.is_selected,
        updated_at=plan_option.updated_at.isoformat(),
    )


def serialize_session_memory_message(message) -> SessionMemoryMessageResponse:
    """把最近消息压缩成会话记忆视图。"""
    raw_preview = " ".join((message.content or "").split())
    preview = raw_preview[:120] if len(raw_preview) <= 120 else f"{raw_preview[:119]}…"
    return SessionMemoryMessageResponse(
        id=str(message.id),
        role=message.role,
        content_preview=preview,
        plan_option_id=str(message.plan_option_id) if message.plan_option_id else None,
        created_at=message.created_at.isoformat(),
    )


def serialize_user_preference(item) -> UserPreferenceResponse:
    """把用户偏好对象转换成接口响应。"""
    return UserPreferenceResponse(
        id=str(item.id),
        category=item.preference_category,
        key=item.preference_key,
        value=item.preference_value or {},
        source=item.source,
        confidence=str(item.confidence),
        updated_at=item.updated_at.isoformat(),
    )


def serialize_session_event(item) -> SessionEventResponse:
    """把会话事件对象转换成接口响应。"""
    return SessionEventResponse(
        id=str(item.id),
        event_type=item.event_type,
        message_id=str(item.message_id) if item.message_id else None,
        plan_option_id=str(item.plan_option_id) if item.plan_option_id else None,
        comparison_id=str(item.comparison_id) if item.comparison_id else None,
        trip_id=str(item.trip_id) if item.trip_id else None,
        event_payload=item.event_payload or {},
        created_at=item.created_at.isoformat(),
    )


def serialize_history_recall_log(item) -> HistoryRecallLogResponse:
    """把历史召回日志对象转换成接口响应。"""
    payload = item.recall_payload or {}
    return HistoryRecallLogResponse(
        id=str(item.id),
        recall_type=item.recall_type,
        matched_record_type=item.matched_record_type,
        matched_record_id=str(item.matched_record_id) if item.matched_record_id else None,
        matched_count=item.matched_count,
        confidence=str(item.confidence) if item.confidence is not None else None,
        summary=payload.get("summary"),
        decision_summary=payload.get("decision_summary"),
        created_at=item.created_at.isoformat(),
    )


def serialize_session_checkpoint(item) -> SessionCheckpointResponse:
    """把检查点事件转换成接口响应。"""
    payload = item.event_payload or {}
    return SessionCheckpointResponse(
        id=str(item.id),
        label=payload.get("label") or "未命名检查点",
        active_plan_option_id=payload.get("active_plan_option_id"),
        active_comparison_id=payload.get("active_comparison_id"),
        snapshot_scope=payload.get("snapshot_scope"),
        summary_restore_mode=payload.get("summary_restore_mode"),
        created_at=item.created_at.isoformat(),
    )


def serialize_plan_comparison(item) -> PlanComparisonSummaryResponse:
    """把方案比较对象转换成接口响应。"""
    return PlanComparisonSummaryResponse(
        id=str(item.id),
        name=item.name,
        status=item.status,
        summary=item.summary,
        recommended_option_id=str(item.recommended_option_id) if item.recommended_option_id else None,
        comparison_dimensions=item.comparison_dimensions or [],
        updated_at=item.updated_at.isoformat(),
    )


def serialize_trip_summary(item) -> TripSummaryResponse:
    """把正式行程对象转换成摘要响应。"""
    return TripSummaryResponse(
        id=str(item.id),
        title=item.title,
        status=item.status,
        primary_destination=item.primary_destination,
        total_days=item.total_days,
        summary=item.summary,
        source_plan_option_id=str(item.source_plan_option_id) if item.source_plan_option_id else None,
        selected_from_comparison_id=(
            str(item.selected_from_comparison_id)
            if item.selected_from_comparison_id
            else None
        ),
        confirmed_at=item.confirmed_at.isoformat() if item.confirmed_at else None,
        updated_at=item.updated_at.isoformat(),
    )


def serialize_trip_detail(item) -> TripDetailResponse:
    """把正式行程对象转换成详情响应。"""
    return TripDetailResponse(
        id=str(item.id),
        title=item.title,
        status=item.status,
        primary_destination=item.primary_destination,
        total_days=item.total_days,
        summary=item.summary,
        plan_markdown=item.plan_markdown,
        source_plan_option_id=str(item.source_plan_option_id) if item.source_plan_option_id else None,
        selected_from_comparison_id=(
            str(item.selected_from_comparison_id)
            if item.selected_from_comparison_id
            else None
        ),
        destinations=[
            {
                "id": str(dest.id),
                "sequence_no": dest.sequence_no,
                "destination_name": dest.destination_name,
                "stay_days": dest.stay_days,
                "notes": dest.notes,
            }
            for dest in item.destinations
        ],
        itinerary_days=[
            {
                "id": str(day.id),
                "day_no": day.day_no,
                "trip_date": day.trip_date.isoformat() if day.trip_date else None,
                "city_name": day.city_name,
                "title": day.title,
                "summary": day.summary,
                "items": day.items or [],
            }
            for day in item.itinerary_days
        ],
        confirmed_at=item.confirmed_at.isoformat() if item.confirmed_at else None,
        updated_at=item.updated_at.isoformat(),
    )


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


@app.get("/integrations/amap/geocode")
async def amap_geocode(
    user: CurrentUserDep,
    address: str = Query(..., description="待解析地址"),
    city: str | None = Query(default=None, description="限定城市，可选"),
):
    """地址转经纬度。"""
    service = AmapService()
    try:
        return service.geocode(address=address, city=city)
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/regeo")
async def amap_reverse_geocode(
    user: CurrentUserDep,
    location: str = Query(..., description="经纬度，格式 lng,lat"),
    radius: int = Query(default=1000, ge=1, le=3000, description="查询半径（米）"),
    extensions: str = Query(default="base", description="base 或 all"),
):
    """经纬度转地址。"""
    service = AmapService()
    try:
        return service.reverse_geocode(
            location=location,
            radius=radius,
            extensions=extensions,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/poi")
async def amap_search_poi(
    user: CurrentUserDep,
    keywords: str = Query(..., description="POI 关键字"),
    city: str | None = Query(default=None, description="城市名称，可选"),
    city_limit: bool = Query(default=True, description="是否限制在 city 内搜索"),
    types: str | None = Query(default=None, description="POI 类型编码，可选"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=25),
):
    """POI 搜索。"""
    service = AmapService()
    try:
        return service.search_poi(
            keywords=keywords,
            city=city,
            city_limit=city_limit,
            types=types,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/route/driving")
async def amap_route_driving(
    user: CurrentUserDep,
    origin: str = Query(..., description="起点经纬度，格式 lng,lat"),
    destination: str = Query(..., description="终点经纬度，格式 lng,lat"),
    strategy: int = Query(default=0, ge=0, le=20),
    extensions: str = Query(default="base", description="base 或 all"),
):
    """驾车路线规划。"""
    service = AmapService()
    try:
        return service.route_driving(
            origin=origin,
            destination=destination,
            strategy=strategy,
            extensions=extensions,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/route/walking")
async def amap_route_walking(
    user: CurrentUserDep,
    origin: str = Query(..., description="起点经纬度，格式 lng,lat"),
    destination: str = Query(..., description="终点经纬度，格式 lng,lat"),
):
    """步行路线规划。"""
    service = AmapService()
    try:
        return service.route_walking(origin=origin, destination=destination)
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/route/transit")
async def amap_route_transit(
    user: CurrentUserDep,
    origin: str = Query(..., description="起点经纬度，格式 lng,lat"),
    destination: str = Query(..., description="终点经纬度，格式 lng,lat"),
    city: str = Query(..., description="公交规划所在城市"),
    cityd: str | None = Query(default=None, description="终点城市，可选"),
    strategy: int = Query(default=0, ge=0, le=5),
    nightflag: int = Query(default=0, ge=0, le=1),
    extensions: str = Query(default="base", description="base 或 all"),
):
    """公交/地铁综合路线规划。"""
    service = AmapService()
    try:
        return service.route_transit(
            origin=origin,
            destination=destination,
            city=city,
            cityd=cityd,
            strategy=strategy,
            nightflag=nightflag,
            extensions=extensions,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/weather")
async def amap_weather(
    user: CurrentUserDep,
    city: str = Query(..., description="城市名或城市 adcode"),
    extensions: str = Query(default="base", description="base 为实况，all 为预报"),
):
    """城市天气（高德版本）。"""
    service = AmapService()
    try:
        return service.weather(city=city, extensions=extensions)
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/nearby")
async def amap_search_nearby(
    user: CurrentUserDep,
    location: str = Query(..., description="中心点经纬度，格式 lng,lat"),
    keywords: str | None = Query(default=None, description="关键词，可选"),
    types: str | None = Query(default=None, description="类型编码，可选"),
    radius: int = Query(default=3000, ge=1, le=50000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=25),
    sortrule: str = Query(default="distance", description="distance 或 weight"),
):
    """周边搜索。"""
    service = AmapService()
    try:
        return service.search_nearby(
            location=location,
            keywords=keywords,
            types=types,
            radius=radius,
            page=page,
            page_size=page_size,
            sortrule=sortrule,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/nearby/food")
async def amap_search_nearby_food(
    user: CurrentUserDep,
    location: str = Query(..., description="中心点经纬度，格式 lng,lat"),
    radius: int = Query(default=3000, ge=1, le=10000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=25),
):
    """周边美食搜索。"""
    service = AmapService()
    try:
        return service.search_nearby_food(
            location=location,
            radius=radius,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.get("/integrations/amap/nearby/stays")
async def amap_search_nearby_stays(
    user: CurrentUserDep,
    location: str = Query(..., description="中心点经纬度，格式 lng,lat"),
    keyword: str | None = Query(default=None, description="可选：酒店/民宿"),
    radius: int = Query(default=5000, ge=1, le=15000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=25),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_budget: float | None = Query(default=None, gt=0),
    max_distance_m: int | None = Query(default=None, gt=0),
    include_unknown_budget: bool = Query(default=True),
    include_unknown_rating: bool = Query(default=True),
):
    """周边住宿搜索（酒店/民宿）。"""
    service = AmapService()
    try:
        if (
            min_rating is not None
            or max_budget is not None
            or max_distance_m is not None
        ):
            return service.search_stays_with_filters(
                location=location,
                radius=radius,
                limit=page_size,
                min_rating=min_rating,
                max_budget=max_budget,
                max_distance_m=max_distance_m,
                include_unknown_budget=include_unknown_budget,
                include_unknown_rating=include_unknown_rating,
            )
        return service.search_nearby_stay(
            location=location,
            keyword=keyword,
            radius=radius,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:  # pragma: no cover - 统一映射出口
        _raise_http_for_integration_error(exc)


@app.post("/sessions", response_model=SessionSummaryResponse)
async def create_chat_session(
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """创建一个新的空会话。"""
    session_service = SessionManagementService(db)
    session = session_service.create_session(user_id=user.id, first_message="")
    return serialize_session(session)


@app.get("/sessions", response_model=list[SessionSummaryResponse])
async def get_chat_sessions(
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前演示用户的会话列表。"""
    session_service = SessionManagementService(db)
    sessions = session_service.list_sessions(user_id=user.id)
    return [serialize_session(item) for item in sessions]


@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_chat_session_messages(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回某个会话的消息历史。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    session_service = SessionManagementService(db)
    try:
        session = session_service.get_session_or_raise(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = session_service.list_messages(session_id=session.id)
    return SessionMessagesResponse(
        session_id=str(session.id),
        title=session.title,
        status=session.status,
        messages=[serialize_message(item) for item in messages],
    )


@app.patch("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def rename_chat_session(
    session_id: str,
    payload: SessionRenameRequest,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """重命名某个会话。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    session_service = SessionManagementService(db)
    try:
        session = session_service.get_session_or_raise(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        session = session_service.rename_session(session=session, title=payload.title)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_session(session)


@app.patch("/sessions/{session_id}/archive", response_model=SessionSummaryResponse)
async def archive_chat_session(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """归档某个会话。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    session_service = SessionManagementService(db)
    try:
        session = session_service.get_session_or_raise(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session = session_service.archive_session(session=session)
    return serialize_session(session)


@app.delete("/sessions/{session_id}", response_model=SessionSummaryResponse)
async def delete_chat_session(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """软删除某个会话。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    session_service = SessionManagementService(db)
    try:
        session = session_service.get_session_or_raise(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session = session_service.delete_session(session=session)
    return serialize_session(session)


@app.get("/sessions/{session_id}/memory", response_model=SessionMemoryResponse)
async def get_chat_session_memory(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的摘要、激活方案记忆和最近消息。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        snapshot = workspace_service.get_memory_snapshot(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session = snapshot.session
    context_payload = snapshot.context_payload
    plan_option_views = snapshot.plan_option_views

    return SessionMemoryResponse(
        session_id=str(session.id),
        title=session.title,
        status=session.status,
        summary=context_payload["session_summary"],
        active_plan_option_id=context_payload["active_plan_option_id"],
        active_plan_title=context_payload["active_plan_title"],
        active_plan_summary=context_payload["active_plan_summary"],
        active_comparison_summary=context_payload["active_comparison_summary"],
        user_preference_summary=context_payload["user_preference_summary"],
        recent_messages=[
            serialize_session_memory_message(item)
            for item in context_payload["recent_messages"]
        ],
        plan_options=[serialize_plan_option(item) for item in plan_option_views],
    )


@app.get("/sessions/{session_id}/events", response_model=list[SessionEventResponse])
async def get_chat_session_events(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的审计事件列表。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        items = workspace_service.list_events(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [serialize_session_event(item) for item in items]


@app.get("/sessions/{session_id}/checkpoints", response_model=list[SessionCheckpointResponse])
async def get_chat_session_checkpoints(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的检查点列表。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        items = workspace_service.list_checkpoints(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [serialize_session_checkpoint(item) for item in items]


@app.post("/sessions/{session_id}/checkpoints", response_model=SessionCheckpointResponse)
async def create_chat_session_checkpoint(
    session_id: str,
    payload: CheckpointCreateRequest,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """为当前会话创建检查点。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        checkpoint = workspace_service.create_checkpoint(
            session_id=session_uuid,
            user_id=user.id,
            label=payload.label,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return serialize_session_checkpoint(checkpoint)


@app.post(
    "/sessions/{session_id}/checkpoints/{checkpoint_id}/rewind",
    response_model=SessionSummaryResponse,
)
async def rewind_chat_session_checkpoint(
    session_id: str,
    checkpoint_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """把当前会话回退到某个检查点。"""
    try:
        session_uuid = uuid.UUID(session_id)
        checkpoint_uuid = uuid.UUID(checkpoint_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        session = workspace_service.rewind_checkpoint(
            session_id=session_uuid,
            checkpoint_id=checkpoint_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_session(session)


@app.get("/sessions/{session_id}/recalls", response_model=list[HistoryRecallLogResponse])
async def get_chat_session_recalls(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的历史召回日志。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    workspace_service = SessionWorkspaceService(db)
    try:
        items = workspace_service.list_recalls(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [serialize_history_recall_log(item) for item in items]


@app.get("/preferences", response_model=list[UserPreferenceResponse])
async def get_user_preferences(
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前演示用户已经沉淀的长期偏好。"""
    workspace_service = SessionWorkspaceService(db)
    items = workspace_service.list_preferences(user_id=user.id)
    return [serialize_user_preference(item) for item in items]


@app.get("/sessions/{session_id}/plan-options", response_model=SessionPlanOptionsResponse)
async def get_session_plan_options(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的候选方案列表。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    plan_option_service = PlanOptionService(db)
    try:
        session, items = plan_option_service.list_plan_option_views(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionPlanOptionsResponse(
        session_id=str(session.id),
        active_plan_option_id=(
            str(session.active_plan_option_id) if session.active_plan_option_id else None
        ),
        items=[serialize_plan_option(item) for item in items],
    )


@app.post("/sessions/{session_id}/plan-options", response_model=PlanOptionSummaryResponse)
async def create_session_plan_option(
    session_id: str,
    payload: PlanOptionCreateRequest,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """创建一个候选方案。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    try:
        plan_option_service = PlanOptionService(db)
        plan_option = plan_option_service.create_option(
            session_id=session_uuid,
            user_id=user.id,
            title=payload.title,
            primary_destination=payload.primary_destination,
            travel_start_date=parse_optional_date(payload.travel_start_date),
            travel_end_date=parse_optional_date(payload.travel_end_date),
            total_days=payload.total_days,
            summary=payload.summary,
            plan_markdown=payload.plan_markdown,
            activate=payload.activate,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_plan_option(plan_option)


@app.post(
    "/sessions/{session_id}/plan-options/from-latest-message",
    response_model=PlanOptionSaveResultResponse,
)
async def create_plan_option_from_latest_message(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """根据当前会话的最新助手回复生成候选方案。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    try:
        plan_option_service = PlanOptionService(db)
        plan_options = plan_option_service.create_options_from_latest_message(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlanOptionSaveResultResponse(
        created_count=len(plan_options),
        message=(
            f"已保存 {len(plan_options)} 个候选方案"
            if len(plan_options) > 1
            else "已保存 1 个候选方案"
        ),
        items=[serialize_plan_option(item) for item in plan_options],
    )


@app.patch(
    "/sessions/{session_id}/plan-options/{plan_option_id}/activate",
    response_model=PlanOptionSummaryResponse,
)
async def activate_session_plan_option(
    session_id: str,
    plan_option_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """把候选方案设为当前会话的激活方案。"""
    try:
        session_uuid = uuid.UUID(session_id)
        plan_option_uuid = uuid.UUID(plan_option_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    plan_option_service = PlanOptionService(db)
    try:
        plan_option = plan_option_service.activate_option(
            session_id=session_uuid,
            plan_option_id=plan_option_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return serialize_plan_option(plan_option)


@app.post(
    "/sessions/{session_id}/plan-options/{plan_option_id}/copy",
    response_model=PlanOptionSummaryResponse,
)
async def copy_session_plan_option(
    session_id: str,
    plan_option_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """复制一个候选方案，作为新的版本。"""
    try:
        session_uuid = uuid.UUID(session_id)
        plan_option_uuid = uuid.UUID(plan_option_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    plan_option_service = PlanOptionService(db)
    try:
        copied_option = plan_option_service.fork_option(
            session_id=session_uuid,
            plan_option_id=plan_option_uuid,
            user_id=user.id,
            activate=True,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_plan_option(copied_option)


@app.patch(
    "/sessions/{session_id}/plan-options/{plan_option_id}/archive",
    response_model=PlanOptionSummaryResponse,
)
async def archive_session_plan_option(
    session_id: str,
    plan_option_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """归档一个候选方案。"""
    try:
        session_uuid = uuid.UUID(session_id)
        plan_option_uuid = uuid.UUID(plan_option_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    plan_option_service = PlanOptionService(db)
    try:
        plan_option = plan_option_service.archive_option(
            session_id=session_uuid,
            plan_option_id=plan_option_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_plan_option(plan_option)


@app.delete(
    "/sessions/{session_id}/plan-options/{plan_option_id}",
    response_model=PlanOptionSummaryResponse,
)
async def delete_session_plan_option(
    session_id: str,
    plan_option_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """软删除一个候选方案。"""
    try:
        session_uuid = uuid.UUID(session_id)
        plan_option_uuid = uuid.UUID(plan_option_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    plan_option_service = PlanOptionService(db)
    try:
        plan_option = plan_option_service.delete_option(
            session_id=session_uuid,
            plan_option_id=plan_option_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_plan_option(plan_option)


@app.get("/sessions/{session_id}/comparisons", response_model=SessionComparisonsResponse)
async def get_session_comparisons(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话的方案比较列表。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    comparison_service = ComparisonService(db)
    try:
        session, items = comparison_service.list_comparisons(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionComparisonsResponse(
        session_id=str(session.id),
        active_comparison_id=(
            str(session.active_comparison_id) if session.active_comparison_id else None
        ),
        items=[serialize_plan_comparison(item) for item in items],
    )


@app.post("/sessions/{session_id}/comparisons", response_model=PlanComparisonSummaryResponse)
async def create_session_comparison(
    session_id: str,
    payload: PlanComparisonCreateRequest,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """创建或更新当前会话的方案比较。"""
    try:
        session_uuid = uuid.UUID(session_id)
        option_ids = [uuid.UUID(item) for item in payload.plan_option_ids]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    comparison_service = ComparisonService(db)
    try:
        comparison = comparison_service.create_or_update_comparison(
            session_id=session_uuid,
            user_id=user.id,
            plan_option_ids=option_ids,
            name=payload.name,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_plan_comparison(comparison)


@app.get("/sessions/{session_id}/trips", response_model=SessionTripsResponse)
async def get_session_trips(
    session_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回当前会话沉淀出的正式行程。"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="session_id 格式不正确") from exc

    trip_service = TripService(db)
    try:
        session, items = trip_service.list_trips(
            session_id=session_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionTripsResponse(
        session_id=str(session.id),
        items=[serialize_trip_summary(item) for item in items],
    )


@app.post("/sessions/{session_id}/trips", response_model=TripSummaryResponse)
async def create_session_trip(
    session_id: str,
    payload: TripCreateRequest,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """从当前候选方案或方案比较生成正式行程。"""
    try:
        session_uuid = uuid.UUID(session_id)
        plan_option_uuid = uuid.UUID(payload.plan_option_id) if payload.plan_option_id else None
        comparison_uuid = uuid.UUID(payload.comparison_id) if payload.comparison_id else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    trip_service = TripService(db)
    try:
        trip = trip_service.create_trip(
            session_id=session_uuid,
            user_id=user.id,
            plan_option_id=plan_option_uuid,
            comparison_id=comparison_uuid,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_trip_summary(trip)


@app.get("/sessions/{session_id}/trips/{trip_id}", response_model=TripDetailResponse)
async def get_session_trip_detail(
    session_id: str,
    trip_id: str,
    user: CurrentUserDep,
    db: Session = Depends(get_db),
):
    """返回某个正式行程的详情。"""
    try:
        session_uuid = uuid.UUID(session_id)
        trip_uuid = uuid.UUID(trip_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ID 格式不正确") from exc

    trip_service = TripService(db)
    try:
        trip = trip_service.get_trip_or_raise(
            session_id=session_uuid,
            trip_id=trip_uuid,
            user_id=user.id,
        )
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return serialize_trip_detail(trip)


@app.post("/chat")
async def chat(
    user: CurrentUserDep,
    message: str = Form(...),
    history: str = Form("[]"),
    session_id: str = Form(""),
    db: Session = Depends(get_db),
):
    """接收消息并返回标准 SSE 流。"""
    user_input = message.strip()
    if not user_input:
        return StreamingResponse(
            iter([format_sse("error", {"message": "消息不能为空"})]),
            media_type="text/event-stream",
        )

    is_new_session = False
    session_management_service = SessionManagementService(db)
    message_service = MessageService(db)

    if session_id.strip():
        try:
            session_uuid = uuid.UUID(session_id.strip())
        except ValueError:
            return StreamingResponse(
                iter([format_sse("error", {"message": "session_id 格式不正确"})]),
                media_type="text/event-stream",
            )

        try:
            session = session_management_service.get_session_or_raise(
                session_id=session_uuid,
                user_id=user.id,
            )
        except ServiceNotFoundError:
            return StreamingResponse(
                iter([format_sse("error", {"message": "会话不存在或不属于当前用户"})]),
                media_type="text/event-stream",
            )
    else:
        session = session_management_service.create_session(
            user_id=user.id,
            first_message=user_input,
        )
        is_new_session = True

    fallback_history = build_history_messages(history)
    session_service = SessionService(db)
    memory_service = MemoryService(db)
    session_action = session_service.apply_user_input(
        session=session,
        user_id=user.id,
        user_input=user_input,
    )

    message_service.save_user_message(session=session, user_id=user.id, content=user_input)

    def event_stream():
        yield format_sse(
            "session",
            {
                "session_id": str(session.id),
                "is_new": is_new_session,
                "title": session.title,
            },
        )
        yield format_sse(
            "intent",
            session_action.route.to_intent_payload(),
        )

        if session_action.clarification_message:
            clarification_message = session_action.clarification_message
            yield format_sse("phase", {"value": "answering", "label": "正在确认你的意图"})
            yield format_sse("token", {"content": clarification_message})
            message_service.save_assistant_message(
                session=session,
                user_id=user.id,
                content=clarification_message,
                tool_outputs=[],
                has_error=False,
            )
            yield format_sse("done", {"status": "ok"})
            return

        input_messages = memory_service.build_runtime_context_messages(
            session=session,
            fallback_history=fallback_history,
            extra_sections=session_action.extra_sections,
            current_user_input=user_input,
            recall_result=session_action.recall,
        )
        agent = get_agent()
        input_data = {"messages": input_messages}
        has_tool_output = False
        has_answer_token = False
        tool_outputs = []
        final_answer = ""

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
                        tool_outputs.append(text)
                        yield format_sse("tool", {"content": text})

                elif node == "llm_node" and text:
                    if not has_answer_token:
                        has_answer_token = True
                        yield format_sse(
                            "phase",
                            {"value": "answering", "label": "正在整理最终建议"},
                        )
                    final_answer += text
                    yield format_sse("token", {"content": text})

            if final_answer.strip():
                message_service.save_assistant_message(
                    session=session,
                    user_id=user.id,
                    content=final_answer,
                    tool_outputs=tool_outputs,
                    has_error=False,
                )
            yield format_sse("done", {"status": "ok"})
        except Exception as exc:
            error_message = f"请求失败：{exc}"
            message_service.save_assistant_message(
                session=session,
                user_id=user.id,
                content=final_answer.strip() or error_message,
                tool_outputs=tool_outputs,
                has_error=True,
            )
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
