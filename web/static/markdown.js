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

    text = text.replace(/^(#{1,6})(\*\*|\S)/gm, (match, hashes, nextPart) => {
      if (/^\s/.test(nextPart)) {
        return match;
      }
      return `${hashes} ${nextPart}`;
    });

    text = text.replace(/^(#{1,6})\s+\*\*(.*?)\*\*\s*$/gm, "$1 $2");
    text = text.replace(/^\s*(?:--|—|–){3,}\s*$/gm, "---");
    text = text.replace(/^(\s*[-*])(?![-*])(\*\*|\S)/gm, (match, bullet, nextPart) => {
      if (/^\s/.test(nextPart)) {
        return match;
      }
      return `${bullet} ${nextPart}`;
    });
    text = text.replace(/^(\s*\d+\.)((?!\s).)/gm, "$1 $2");
    text = text.replace(/^\s*(\*\*|__)\s*$/gm, "");
    text = text.replace(/^\s*#{1,6}\s*(\*\*|__)?\s*$/gm, "");
    text = text.replace(/^\s*(\*\*|__)\s*#{1,6}\s*$/gm, "");
    text = text.replace(/\n{3,}/g, "\n\n");

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
