from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendLayoutContractTests(unittest.TestCase):
    def test_main_template_uses_single_trip_panel_without_header_export_buttons(self):
        template = (PROJECT_ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="currentTripPanel"', template)
        self.assertNotIn('data-header-menu', template)
        self.assertNotIn('id="exportMarkdownBtn"', template)
        self.assertNotIn('id="exportPdfBtn"', template)
        self.assertNotIn('id="archiveSessionBtn"', template)
        self.assertNotIn('id="createCheckpointBtn"', template)
        self.assertNotIn('class="workflow-auto-strip"', template)
        self.assertNotIn('class="session-state-strip"', template)

    def test_app_js_uses_session_menu_export_and_single_cover_panel(self):
        script = (PROJECT_ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")

        self.assertNotIn('data-role="workspace"', script)
        self.assertIn('data-action="pin"', script)
        self.assertNotIn('data-action="archive"', script)
        self.assertIn('data-action="export-markdown"', script)
        self.assertIn('data-action="export-pdf"', script)
        self.assertIn("downloadTripExport", script)
        self.assertIn("renderCurrentTripPanel", script)
        self.assertIn("${renderTripDocumentMarkup(trip)}", script)
        self.assertIn("isReplyStreaming", script)
        self.assertIn("tripPanelPendingRefresh", script)
        self.assertIn("tripPanelBaselineSignature", script)
        self.assertNotIn("${renderTripArrivalSection(trip)}", script)
        self.assertNotIn("${renderTripMapPreviewSection(trip)}", script)
        self.assertNotIn("${renderTripDecisionMarkup(", script)
        self.assertNotIn("trip-hero-facts", script)
        self.assertNotIn("trip-hero-insights", script)
        self.assertNotIn("trip-hero-compact-rows", script)
        self.assertNotIn("trip-hero-row-map", script)
        self.assertNotIn("headerActionMenu", script)
        self.assertNotIn(".chat-header-actions-compact {\n  display: none !important;", css)


if __name__ == "__main__":
    unittest.main()
