"""Trip 导出服务。"""

from __future__ import annotations

import html
import re
from datetime import datetime
from io import BytesIO
from typing import Any

from services.errors import ServiceConfigError
from services.trip_document_service import TripDocumentService


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _slugify_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", "-", value or "").strip()
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized.strip("-") or "trip-document"


class TripExportService:
    """把当前 Trip 导出为 Markdown / PDF。"""

    PRINT_STYLES = """
      :root {
        color-scheme: light;
        --bg: #fbf6ef;
        --paper: #fffdf9;
        --ink: #2f261d;
        --muted: #7c6652;
        --line: #e7dacb;
        --accent: #8a5a36;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 40px;
        background: linear-gradient(180deg, var(--bg), #f3eadf);
        color: var(--ink);
        font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
        line-height: 1.75;
      }
      .document-shell {
        max-width: 920px;
        margin: 0 auto;
        padding: 36px 42px;
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: 0 18px 40px rgba(76, 54, 29, 0.08);
      }
      h1, h2, h3, h4 { color: #241a12; line-height: 1.35; }
      h1 {
        margin: 0 0 18px;
        font-size: 30px;
      }
      h2 {
        margin: 28px 0 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--line);
        font-size: 22px;
      }
      h3 {
        margin: 22px 0 10px;
        font-size: 18px;
      }
      p, li { font-size: 14px; }
      ul, ol { padding-left: 22px; }
      code, pre {
        font-family: "Cascadia Mono", "Consolas", monospace;
        background: #f7efe6;
        border-radius: 8px;
      }
      code { padding: 2px 6px; }
      pre {
        padding: 14px 16px;
        overflow: hidden;
        white-space: pre-wrap;
      }
      blockquote {
        margin: 14px 0;
        padding: 10px 14px;
        border-left: 4px solid #d2b08f;
        color: var(--muted);
        background: #fcf7f1;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 14px 0;
      }
      th, td {
        padding: 10px 12px;
        border: 1px solid var(--line);
        text-align: left;
      }
      th {
        background: #f8f0e6;
        font-weight: 700;
      }
      hr {
        margin: 24px 0;
        border: none;
        border-top: 1px solid var(--line);
      }
    """

    def ensure_document_markdown(self, trip) -> str:
        constraints = dict(getattr(trip, "constraints", None) or {})
        markdown = _safe_text(constraints.get("document_markdown"))
        if markdown:
            return markdown

        structured_context = constraints.get("structured_context")
        if not isinstance(structured_context, dict):
            structured_context = {}

        delivery_payload = constraints.get("delivery_payload")
        if not isinstance(delivery_payload, dict) or not delivery_payload:
            delivery_payload = TripDocumentService.build_delivery_payload(
                trip=trip,
                structured_context=structured_context,
            )

        markdown = TripDocumentService.build_document_markdown(delivery_payload)
        return markdown or "# 旅行方案\n\n当前正式行程还没有可导出的内容。"

    def build_markdown_filename(self, trip) -> str:
        base = _safe_text(getattr(trip, "title", None)) or _safe_text(
            getattr(trip, "primary_destination", None)
        )
        if not base:
            base = "trip-document"
        return f"{_slugify_filename(base)}.md"

    def build_pdf_filename(self, trip) -> str:
        return self.build_markdown_filename(trip).rsplit(".", 1)[0] + ".pdf"

    def render_printable_html(self, *, trip, markdown_text: str) -> str:
        title = html.escape(_safe_text(getattr(trip, "title", None)) or "旅行方案")
        body = self._markdown_to_html(markdown_text)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{self.PRINT_STYLES}</style>
</head>
<body>
  <main class="document-shell">
    {body}
  </main>
</body>
</html>"""

    def build_pdf_bytes(self, *, trip, markdown_text: str) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:  # pragma: no cover - 依赖缺失时走接口错误
            raise ServiceConfigError(
                "缺少 PDF 导出依赖 reportlab，请先安装 requirements.txt 中的依赖。"
            ) from exc

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=_safe_text(getattr(trip, "title", None)) or "旅行方案",
        )
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        styles = getSampleStyleSheet()
        base = ParagraphStyle(
            "TripBody",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=10.5,
            leading=16,
            spaceAfter=6,
        )
        heading_1 = ParagraphStyle(
            "TripHeading1",
            parent=base,
            fontSize=20,
            leading=28,
            spaceBefore=4,
            spaceAfter=12,
        )
        heading_2 = ParagraphStyle(
            "TripHeading2",
            parent=base,
            fontSize=15,
            leading=22,
            spaceBefore=10,
            spaceAfter=8,
        )
        heading_3 = ParagraphStyle(
            "TripHeading3",
            parent=base,
            fontSize=12.5,
            leading=18,
            spaceBefore=8,
            spaceAfter=6,
        )
        bullet = ParagraphStyle(
            "TripBullet",
            parent=base,
            leftIndent=12,
            firstLineIndent=-8,
        )

        story = []
        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                story.append(Spacer(1, 4))
                continue
            text = html.escape(line)
            if line.startswith("# "):
                story.append(Paragraph(html.escape(line[2:].strip()), heading_1))
                continue
            if line.startswith("## "):
                story.append(Paragraph(html.escape(line[3:].strip()), heading_2))
                continue
            if line.startswith("### "):
                story.append(Paragraph(html.escape(line[4:].strip()), heading_3))
                continue
            if re.match(r"^\s*[-*]\s+", line):
                bullet_text = re.sub(r"^\s*[-*]\s+", "", line)
                story.append(Paragraph("• " + html.escape(bullet_text), bullet))
                continue
            if re.match(r"^\s*\d+\.\s+", line):
                story.append(Paragraph(text, bullet))
                continue
            story.append(Paragraph(text, base))

        doc.build(story)
        return buffer.getvalue()

    def _markdown_to_html(self, markdown_text: str) -> str:
        try:
            import markdown as markdown_lib
        except ImportError:  # pragma: no cover - 无依赖时使用内置降级
            return self._fallback_markdown_to_html(markdown_text)

        return markdown_lib.markdown(
            markdown_text,
            extensions=["extra", "tables", "sane_lists", "nl2br"],
            output_format="html5",
        )

    def _fallback_markdown_to_html(self, markdown_text: str) -> str:
        lines = markdown_text.splitlines()
        output: list[str] = []
        list_buffer: list[str] = []

        def flush_list() -> None:
            nonlocal list_buffer
            if not list_buffer:
                return
            output.append("<ul>")
            output.extend(list_buffer)
            output.append("</ul>")
            list_buffer = []

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                flush_list()
                continue
            if stripped.startswith("# "):
                flush_list()
                output.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
                continue
            if stripped.startswith("## "):
                flush_list()
                output.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
                continue
            if stripped.startswith("### "):
                flush_list()
                output.append(f"<h3>{html.escape(stripped[4:].strip())}</h3>")
                continue
            if stripped in {"---", "***"}:
                flush_list()
                output.append("<hr>")
                continue
            if re.match(r"^[-*]\s+", stripped):
                list_buffer.append(f"<li>{html.escape(re.sub(r'^[-*]\\s+', '', stripped))}</li>")
                continue
            flush_list()
            output.append(f"<p>{html.escape(stripped)}</p>")

        flush_list()
        return "\n".join(output)
