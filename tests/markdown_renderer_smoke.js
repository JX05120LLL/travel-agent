const assert = require("assert");
const path = require("path");

const markdown = require(path.resolve(__dirname, "..", "web", "static", "markdown.js"));

function renderInline(value) {
  return String(value || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

function fakeParse(source) {
  const lines = String(source || "").split("\n");
  const parts = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    if (/^####\s+/.test(trimmed)) {
      parts.push(`<h4>${renderInline(trimmed.replace(/^####\s+/, ""))}</h4>`);
      index += 1;
      continue;
    }
    if (/^###\s+/.test(trimmed)) {
      parts.push(`<h3>${renderInline(trimmed.replace(/^###\s+/, ""))}</h3>`);
      index += 1;
      continue;
    }
    if (/^---$/.test(trimmed)) {
      parts.push("<hr>");
      index += 1;
      continue;
    }
    if (/^>\s+/.test(trimmed)) {
      parts.push(`<blockquote>${renderInline(trimmed.replace(/^>\s+/, ""))}</blockquote>`);
      index += 1;
      continue;
    }
    if (/^\|/.test(trimmed) && index + 1 < lines.length && /^\|\s*:?-{3,}:?/.test(lines[index + 1].trim())) {
      parts.push("<table><tr><td>ok</td></tr></table>");
      index += 3;
      continue;
    }
    parts.push(`<p>${renderInline(trimmed)}</p>`);
    index += 1;
  }
  return parts.join("");
}

const renderer = markdown.createRenderer({
  markedLib: { parse: fakeParse, setOptions() {} },
  domPurify: { sanitize(html) { return html; } },
});

const source = [
  "开头说明###**每日行程详解**",
  "####① 到达方式",
  ">请以 12306 官方为准",
  "--",
  "| 时段 | 活动 |",
  "| --- | --- |",
  "| 上午 | 抵达 |",
  "普通文本 **重点**",
].join("\n");

const normalized = renderer.normalizeMarkdown(source);
assert.ok(normalized.includes("### 每日行程详解"), normalized);
assert.ok(normalized.includes("#### ① 到达方式"), normalized);
assert.ok(normalized.includes("> 请以 12306 官方为准"), normalized);
assert.ok(normalized.includes("| 时段 | 活动 |"), normalized);

const html = renderer.renderMarkdownHtml(source);
assert.ok(html.includes("<h3>每日行程详解</h3>"), html);
assert.ok(html.includes("<h4>① 到达方式</h4>"), html);
assert.ok(html.includes("<blockquote>请以 12306 官方为准</blockquote>"), html);
assert.ok(html.includes("<hr>"), html);
assert.ok(html.includes("<table>"), html);
assert.ok(html.includes("<strong>重点</strong>"), html);
assert.ok(!html.includes("###**"), html);
assert.ok(!html.includes("| --- |"), html);

console.log("markdown renderer smoke passed");
