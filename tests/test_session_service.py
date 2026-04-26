import sys
import types
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")
    httpx_module.Client = object
    httpx_module.get = MagicMock()
    httpx_module.TimeoutException = Exception
    httpx_module.HTTPStatusError = Exception
    httpx_module.HTTPError = Exception
    sys.modules["httpx"] = httpx_module

if "langchain_core.messages" not in sys.modules or "langchain_core.tools" not in sys.modules:
    langchain_core = sys.modules.get("langchain_core") or types.ModuleType("langchain_core")
    messages_module = sys.modules.get("langchain_core.messages") or types.ModuleType("langchain_core.messages")
    tools_module = sys.modules.get("langchain_core.tools") or types.ModuleType("langchain_core.tools")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    def tool(func=None, *args, **kwargs):
        if func is None:
            return lambda inner: inner
        return func

    messages_module.AIMessage = _Message
    messages_module.HumanMessage = _Message
    messages_module.SystemMessage = _Message
    tools_module.tool = tool
    langchain_core.messages = messages_module
    langchain_core.tools = tools_module
    sys.modules["langchain_core"] = langchain_core
    sys.modules["langchain_core.messages"] = messages_module
    sys.modules["langchain_core.tools"] = tools_module

from db.models import ChatSession
from services.intent_router import IntentRouter, SessionRouteResult
from services.session_service import SessionService


class SessionServiceTests(unittest.TestCase):
    @patch("services.intent_router.list_plan_options")
    @patch("services.intent_router.get_active_plan_option")
    def test_intent_router_does_not_treat_descriptive_bijiao_as_plan_comparison(
        self,
        get_active_plan_option,
        list_plan_options,
    ):
        get_active_plan_option.return_value = None
        list_plan_options.return_value = []
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="汉中出游",
        )

        route = IntentRouter(db=MagicMock()).route(
            session=session,
            user_id=session.user_id,
            user_input=(
                "我现在打算去汉中旅游三天两夜，从西安北站出发。"
                "我想第一天去当地早餐，之后去第一个景点游玩，"
                "中午找一家比较有特色的餐厅吃饭。"
            ),
        )

        self.assertEqual("create_new_option", route.action)
        self.assertFalse(route.needs_confirmation)

    @patch("services.intent_router.list_plan_options")
    @patch("services.intent_router.get_active_plan_option")
    def test_intent_router_still_recognizes_explicit_plan_comparison_request(
        self,
        get_active_plan_option,
        list_plan_options,
    ):
        option_a = SimpleNamespace(id=uuid.uuid4(), title="汉中轻松版", primary_destination="汉中", summary="")
        option_b = SimpleNamespace(id=uuid.uuid4(), title="汉中深度版", primary_destination="汉中", summary="")
        get_active_plan_option.return_value = option_a
        list_plan_options.return_value = [option_a, option_b]
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="汉中出游",
        )

        route = IntentRouter(db=MagicMock()).route(
            session=session,
            user_id=session.user_id,
            user_input="帮我比较一下这两个汉中方案，看看哪个更适合三天两夜。",
        )

        self.assertEqual("compare_options", route.action)

    @patch("services.session_service.create_session_event")
    @patch("services.session_service.get_active_plan_option")
    def test_apply_user_input_attaches_recall_without_duplicate_extra_section(
        self,
        get_active_plan_option,
        create_session_event,
    ):
        get_active_plan_option.return_value = None
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="成都工作区",
        )
        route = SessionRouteResult(action="recall_history", confidence=0.95)

        service = SessionService(db=MagicMock())
        service.memory_service = MagicMock()
        service.recall_service = MagicMock()
        service.recall_service.search_history.return_value = {
            "summary": "命中了成都亲子行程",
            "matches": [{"record_type": "trip"}],
            "confidence": 0.91,
            "log_id": str(uuid.uuid4()),
            "injection_section": "【本轮历史召回】\n命中了成都亲子行程",
        }

        result = service.apply_user_input(
            session=session,
            user_id=session.user_id,
            user_input="还记得之前成都亲子方案吗",
            route_result=route,
        )

        self.assertEqual(
            service.recall_service.search_history.return_value,
            result.recall,
        )
        self.assertEqual([], result.extra_sections)
        self.assertTrue(
            any(
                call.kwargs.get("event_type") == "history_recall_attached"
                for call in create_session_event.call_args_list
            )
        )
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )

    @patch("services.session_service.create_session_event")
    @patch("services.session_service.get_active_plan_option")
    def test_apply_user_input_adds_one_stop_planning_section_for_new_plan(
        self,
        get_active_plan_option,
        create_session_event,
    ):
        get_active_plan_option.return_value = None
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="杭州工作区",
        )
        route = SessionRouteResult(action="create_new_option", confidence=0.93)

        service = SessionService(db=MagicMock())
        service.memory_service = MagicMock()
        service.plan_option_service = MagicMock()
        service.plan_option_service.create_option.return_value = SimpleNamespace(
            plan_option=SimpleNamespace(
                id=uuid.uuid4(),
                title="杭州两日游方案",
            )
        )

        result = service.apply_user_input(
            session=session,
            user_id=session.user_id,
            user_input="帮我规划杭州两天旅行，预算中等，节奏轻松一点",
            route_result=route,
        )

        self.assertTrue(
            any("【本轮输出要求】" in section for section in result.extra_sections)
        )
        one_stop_section = next(
            section for section in result.extra_sections if "【本轮输出要求】" in section
        )
        self.assertIn("一条龙旅行规划", one_stop_section)
        self.assertIn("酒店推荐", one_stop_section)
        self.assertIn("每日行程", one_stop_section)
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )

    @patch("services.session_service.create_session_event")
    @patch("services.session_service.get_plan_option")
    @patch("services.session_service.get_active_plan_option")
    def test_apply_user_input_does_not_add_one_stop_section_for_forwarding_request(
        self,
        get_active_plan_option,
        get_plan_option,
        create_session_event,
    ):
        active_plan_option = SimpleNamespace(
            id=uuid.uuid4(),
            title="杭州轻松两日游",
        )
        get_active_plan_option.return_value = active_plan_option
        get_plan_option.return_value = active_plan_option
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="杭州工作区",
        )
        route = SessionRouteResult(action="continue_current_option", confidence=0.72)

        service = SessionService(db=MagicMock())
        service.memory_service = MagicMock()

        result = service.apply_user_input(
            session=session,
            user_id=session.user_id,
            user_input="把刚才这版发到飞书",
            route_result=route,
        )

        self.assertTrue(
            any("【本轮工作区动作】" in section for section in result.extra_sections)
        )
        self.assertFalse(
            any("一条龙旅行规划" in section for section in result.extra_sections)
        )
        service.memory_service.refresh_session_memory.assert_called_once_with(
            session=session,
            commit=False,
        )


if __name__ == "__main__":
    unittest.main()
