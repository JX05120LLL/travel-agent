const assert = require("assert");
const path = require("path");

const markdown = require(path.resolve(__dirname, "..", "web", "static", "markdown.js"));

function fakeParse(source) {
  const lines = String(source || "").split("\n");
  const parts = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (/^###\s+/.test(line)) {
      parts.push(`<h3>${line.replace(/^###\s+/, "")}</h3>`);
      index += 1;
      continue;
    }
    if (/^---$/.test(line.trim())) {
      parts.push("<hr>");
      index += 1;
      continue;
    }
    if (/^\|/.test(line) && index + 1 < lines.length && /^\|[:\- ]+\|/.test(lines[index + 1])) {
      parts.push("<table><tr><td>ok</td></tr></table>");
      index += 3;
      continue;
    }
    parts.push(`<p>${line}</p>`);
    index += 1;
  }
  return parts.join("");
}

const renderer = markdown.createRenderer({
  markedLib: { parse: fakeParse, setOptions() {} },
  domPurify: { sanitize(html) { return html; } },
});

const source = [
  "###**每日行程详解**",
  "",
  "---",
  "",
  "| 时段 | 活动 |",
  "| --- | --- |",
  "| 上午 | 抵达 |",
].join("\n");

const normalized = renderer.normalizeMarkdown(source);
assert.ok(normalized.includes("### 每日行程详解"));
assert.ok(normalized.includes("| 时段 | 活动 |"));

const html = renderer.renderMarkdownHtml(source);
assert.ok(html.includes("<h3>每日行程详解</h3>"), html);
assert.ok(html.includes("<hr>"), html);
assert.ok(html.includes("<table>"), html);
assert.ok(!html.includes("###**"), html);
assert.ok(!html.includes("| --- |"), html);

console.log("markdown renderer smoke passed");
