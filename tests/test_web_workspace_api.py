import importlib.util
import unittest
import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient

    import web.app as web_app
    from db.models import HistoryRecallLog, User
else:  # pragma: no cover - 本地未装 fastapi 时仅用于跳过
    web_app = None
    HistoryRecallLog = object
    User = object


def build_user() -> User:
    return User(
        id=uuid.uuid4(),
        username="demo_user",
        email="demo@example.com",
        password_hash="not-used",
        display_name="演示用户",
        status="active",
    )


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi 未安装，跳过 web API 测试")
class WebWorkspaceApiExtraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(web_app.app)

    def setUp(self):
        self.user = build_user()
        self.db = object()
        web_app.app.dependency_overrides[web_app.get_current_user] = lambda: self.user
        web_app.app.dependency_overrides[web_app.get_db] = lambda: self.db

    def tearDown(self):
        web_app.app.dependency_overrides.clear()

    def test_serialize_history_recall_log_includes_decision_summary(self):
        log = HistoryRecallLog(
            id=uuid.uuid4(),
            user_id=self.user.id,
            session_id=uuid.uuid4(),
            query_text="帮我回忆五一杭州方案",
            recall_type="trip",
            matched_record_type="trip",
            matched_record_id=uuid.uuid4(),
            matched_count=1,
            confidence=Decimal("0.91"),
            recall_payload={
                "summary": "命中了五一杭州周末方案",
                "decision_summary": "可直接沿用：五一杭州周末方案",
            },
        )
        log.created_at = datetime(2026, 4, 20, 12, 0, 0)

        payload = web_app.serialize_history_recall_log(log).model_dump()
        self.assertEqual("可直接沿用：五一杭州周末方案", payload["decision_summary"])

    def test_serialize_session_checkpoint_includes_snapshot_scope(self):
        item = SimpleNamespace(
            id=uuid.uuid4(),
            event_payload={
                "label": "比较前快照",
                "active_plan_option_id": str(uuid.uuid4()),
                "active_comparison_id": str(uuid.uuid4()),
                "snapshot_scope": {
                    "restores_plan_options": True,
                    "does_not_restore_messages": True,
                },
                "summary_restore_mode": "restore_seed_then_refresh_from_messages",
            },
            created_at=datetime(2026, 4, 20, 12, 30, 0),
        )

        payload = web_app.serialize_session_checkpoint(item).model_dump()
        self.assertTrue(payload["snapshot_scope"]["does_not_restore_messages"])
        self.assertEqual(
            "restore_seed_then_refresh_from_messages",
            payload["summary_restore_mode"],
        )

    @patch("web.app.TripExportService")
    def test_serialize_trip_detail_backfills_document_markdown_when_missing(self, trip_export_cls):
        trip_export_cls.return_value.ensure_document_markdown.return_value = "# 补齐后的行程单"
        trip = SimpleNamespace(
            id=uuid.uuid4(),
            title="上海两日游",
            status="confirmed",
            primary_destination="上海",
            total_days=2,
            summary="正文需要与导出一致",
            plan_markdown=None,
            constraints={
                "structured_context": {},
                "delivery_payload": {},
                "document_markdown": None,
                "price_confidence_summary": None,
            },
            source_plan_option_id=None,
            selected_from_comparison_id=None,
            destinations=[],
            itinerary_days=[],
            confirmed_at=None,
            updated_at=datetime(2026, 4, 25, 12, 0, 0),
        )

        payload = web_app.serialize_trip_detail(trip).model_dump()

        self.assertEqual("# 补齐后的行程单", payload["document_markdown"])
        trip_export_cls.return_value.ensure_document_markdown.assert_called_once_with(trip)

    @patch("web.app.TripService")
    def test_create_session_trip_serializes_created_trip(
        self,
        trip_service_cls,
    ):
        session_id = uuid.uuid4()
        plan_option_id = uuid.uuid4()
        comparison_id = uuid.uuid4()
        trip_id = uuid.uuid4()

        trip_service = trip_service_cls.return_value
        trip_service.create_trip.return_value = SimpleNamespace(
            id=trip_id,
            title="杭州正式行程",
            status="confirmed",
            source_plan_option_id=plan_option_id,
            primary_destination="杭州",
            total_days=2,
            summary="西湖 + 河坊街周末方案",
            selected_from_comparison_id=comparison_id,
            confirmed_at=datetime(2026, 4, 20, 12, 0, 0),
            updated_at=datetime(2026, 4, 20, 12, 5, 0),
        )

        response = self.client.post(
            f"/sessions/{session_id}/trips",
            json={
                "plan_option_id": str(plan_option_id),
                "comparison_id": str(comparison_id),
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(str(trip_id), payload["id"])
        self.assertEqual(str(plan_option_id), payload["source_plan_option_id"])
        self.assertEqual(str(comparison_id), payload["selected_from_comparison_id"])

        _, kwargs = trip_service.create_trip.call_args
        self.assertEqual(session_id, kwargs["session_id"])
        self.assertEqual(plan_option_id, kwargs["plan_option_id"])
        self.assertEqual(comparison_id, kwargs["comparison_id"])
        self.assertEqual(self.user.id, kwargs["user_id"])

    @patch("web.app.SessionManagementService")
    def test_pin_chat_session_updates_state(self, session_management_cls):
        session_id = uuid.uuid4()
        pinned_at = datetime(2026, 4, 24, 9, 30, 0)

        service = session_management_cls.return_value
        service.get_session_or_raise.return_value = SimpleNamespace(
            id=session_id,
            title="杭州两日游",
            status="active",
            summary=None,
            latest_user_message=None,
            is_pinned=False,
            pinned_at=None,
            created_at=datetime(2026, 4, 24, 9, 0, 0),
            updated_at=datetime(2026, 4, 24, 9, 0, 0),
            last_message_at=datetime(2026, 4, 24, 9, 0, 0),
        )
        service.set_session_pinned.return_value = SimpleNamespace(
            id=session_id,
            title="杭州两日游",
            status="active",
            summary=None,
            latest_user_message=None,
            is_pinned=True,
            pinned_at=pinned_at,
            created_at=datetime(2026, 4, 24, 9, 0, 0),
            updated_at=datetime(2026, 4, 24, 9, 30, 0),
            last_message_at=datetime(2026, 4, 24, 9, 0, 0),
        )

        response = self.client.patch(
            f"/sessions/{session_id}/pin",
            json={"is_pinned": True},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["is_pinned"])
        self.assertEqual(pinned_at.isoformat(), payload["pinned_at"])
        self.assertEqual(
            True,
            service.set_session_pinned.call_args.kwargs["is_pinned"],
        )

    @patch("web.app.TripExportService")
    @patch("web.app.TripService")
    def test_export_trip_markdown_uses_document_markdown(
        self,
        trip_service_cls,
        trip_export_cls,
    ):
        session_id = uuid.uuid4()
        trip_id = uuid.uuid4()
        trip = SimpleNamespace(id=trip_id, title="杭州两日游")
        trip_service_cls.return_value.get_trip_or_raise.return_value = trip
        trip_export_cls.return_value.ensure_document_markdown.return_value = "# 杭州两日游\n\n- 西湖"
        trip_export_cls.return_value.build_markdown_filename.return_value = "hangzhou-trip.md"

        response = self.client.get(
            f"/sessions/{session_id}/trips/{trip_id}/export/markdown"
        )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.headers["content-type"].startswith("text/markdown"))
        self.assertIn("attachment;", response.headers["content-disposition"])
        self.assertIn("filename*=", response.headers["content-disposition"])
        self.assertIn("# 杭州两日游", response.text)

    @patch("web.app.TripExportService")
    @patch("web.app.TripService")
    def test_export_trip_pdf_returns_pdf_file(
        self,
        trip_service_cls,
        trip_export_cls,
    ):
        session_id = uuid.uuid4()
        trip_id = uuid.uuid4()
        trip = SimpleNamespace(id=trip_id, title="杭州两日游")
        trip_service_cls.return_value.get_trip_or_raise.return_value = trip
        trip_export_cls.return_value.ensure_document_markdown.return_value = "# 杭州两日游"
        trip_export_cls.return_value.build_pdf_bytes.return_value = b"%PDF-1.4 test"
        trip_export_cls.return_value.build_pdf_filename.return_value = "hangzhou-trip.pdf"

        response = self.client.get(
            f"/sessions/{session_id}/trips/{trip_id}/export/pdf"
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response.headers["content-type"])
        self.assertIn("attachment;", response.headers["content-disposition"])
        self.assertIn("filename*=", response.headers["content-disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()
