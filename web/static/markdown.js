(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.TravelAgentMarkdown = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeMarkdown(rawText) {
    let text = String(rawText || "").replace(/\r\n?/g, "\n");

    text = text
      .replace(/\u00a0/g, " ")
      .replace(/[\u201c\u201d]/g, '"')
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u2014\u2013]{2,}/g, "\n---\n");

    // LLMs often concatenate a new heading after punctuation without a blank line.
    text = text.replace(/([^\n])(\s*)(#{1,6})(?=\s*\S)/g, "$1\n\n$3");

    text = text.replace(/^(#{1,6})(?=\S)/gm, "$1 ");
    text = text.replace(/^(#{1,6})\s+\*\*(.*?)\*\*\s*$/gm, "$1 $2");
    text = text.replace(/^\s*(?:--|---)\s*$/gm, "---");
    text = text.replace(/^(\s*[-*])(?![-*\s])(.+)/gm, "$1 $2");
    text = text.replace(/^(\s*\d+\.)(?!\s)(.+)/gm, "$1 $2");
    text = text.replace(/^\s*(\*\*|__)\s*$/gm, "");
    text = text.replace(/^\s*#{1,6}\s*(\*\*|__)?\s*$/gm, "");
    text = text.replace(/^\s*(\*\*|__)\s*#{1,6}\s*$/gm, "");

    const lines = text.split("\n");
    const normalizedLines = [];
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      const trimmed = line.trim();
      const previous = normalizedLines[normalizedLines.length - 1] || "";
      const next = lines[index + 1] || "";
      const following = lines[index + 1] || "";
      const looksLikeTableRow = /^\|.+\|$/.test(trimmed);
      const nextLooksLikeSeparator = /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(next.trim());
      const currentLooksLikeSeparator = /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(trimmed);

      if (looksLikeTableRow && nextLooksLikeSeparator && previous.trim()) {
        normalizedLines.push("");
      }

      if (/^#{1,6}\s+\S/.test(trimmed) && previous.trim()) {
        normalizedLines.push("");
      }

      if (/^>\S/.test(trimmed)) {
        normalizedLines.push(line.replace(/^>\s*/, "> "));
      } else {
        normalizedLines.push(line);
      }

      if ((looksLikeTableRow || currentLooksLikeSeparator) && following.trim() && !/^\|.+\|$/.test(following.trim())) {
        normalizedLines.push("");
      }
    }

    text = normalizedLines.join("\n").replace(/\n{3,}/g, "\n\n");

    return text.trim();
  }

  function createRenderer({ markedLib, domPurify } = {}) {
    if (markedLib && typeof markedLib.setOptions === "function") {
      markedLib.setOptions({
        gfm: true,
        breaks: true,
      });
    }

    function renderMarkdownHtml(rawText) {
      const normalized = normalizeMarkdown(rawText);
      if (!normalized) {
        return "";
      }

      if (!markedLib || typeof markedLib.parse !== "function") {
        return `<p>${escapeHtml(normalized)}</p>`;
      }

      const html = markedLib.parse(normalized);
      if (!domPurify || typeof domPurify.sanitize !== "function") {
        return html;
      }
      return domPurify.sanitize(html);
    }

    function decorateLinks(container) {
      if (!container || typeof container.querySelectorAll !== "function") {
        return;
      }
      container.querySelectorAll("a").forEach((link) => {
        link.setAttribute("target", "_blank");
        link.setAttribute("rel", "noopener noreferrer");
      });
    }

    function renderIntoElement(container, rawText) {
      if (!container) {
        return "";
      }
      const html = renderMarkdownHtml(rawText);
      container.innerHTML = html;
      decorateLinks(container);
      return html;
    }

    return {
      normalizeMarkdown,
      renderMarkdownHtml,
      decorateLinks,
      renderIntoElement,
    };
  }

  return {
    normalizeMarkdown,
    createRenderer,
  };
});
