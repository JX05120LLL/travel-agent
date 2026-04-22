const { chatEndpoint, sessionsEndpoint, planOptionsPath } = window.TRAVEL_AGENT_CONFIG;
const SESSION_STORAGE_KEY = "travel_agent_session_id";

const chatScroll = document.getElementById("chatScroll");
const messageList = document.getElementById("messageList");
const welcomeCard = document.getElementById("welcomeCard");
const composerForm = document.getElementById("composerForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const newSessionBtn = document.getElementById("newSessionBtn");
const refreshSessionsBtn = document.getElementById("refreshSessionsBtn");
const sessionList = document.getElementById("sessionList");
const sessionEmpty = document.getElementById("sessionEmpty");
const activeSessionTitle = document.getElementById("activeSessionTitle");
const savePlanBtn = document.getElementById("savePlanBtn");
const comparePlansBtn = document.getElementById("comparePlansBtn");
const createTripBtn = document.getElementById("createTripBtn");
const createCheckpointBtn = document.getElementById("createCheckpointBtn");
const rewindCheckpointBtn = document.getElementById("rewindCheckpointBtn");
const renameSessionBtn = document.getElementById("renameSessionBtn");
const archiveSessionBtn = document.getElementById("archiveSessionBtn");
const deleteSessionBtn = document.getElementById("deleteSessionBtn");
const planOptionList = document.getElementById("planOptionList");
const planOptionEmpty = document.getElementById("planOptionEmpty");
const activeIntentBadge = document.getElementById("activeIntentBadge");
const sessionSummaryText = document.getElementById("sessionSummaryText");
const activePlanSummaryText = document.getElementById("activePlanSummaryText");
const comparisonSummaryText = document.getElementById("comparisonSummaryText");
const preferenceList = document.getElementById("preferenceList");
const preferenceEmpty = document.getElementById("preferenceEmpty");
const comparisonList = document.getElementById("comparisonList");
const comparisonEmpty = document.getElementById("comparisonEmpty");
const tripList = document.getElementById("tripList");
const tripEmpty = document.getElementById("tripEmpty");
const checkpointList = document.getElementById("checkpointList");
const checkpointEmpty = document.getElementById("checkpointEmpty");
const eventList = document.getElementById("eventList");
const eventEmpty = document.getElementById("eventEmpty");
const recallList = document.getElementById("recallList");
const recallEmpty = document.getElementById("recallEmpty");
const promptChips = document.querySelectorAll(".prompt-chip");
const workspaceDrawerToggle = document.querySelector(".workspace-drawer-toggle");
const headerActionMenu = document.querySelector("[data-header-menu]");

const conversation = [];
let currentSessionId = localStorage.getItem(SESSION_STORAGE_KEY) || "";
let sessionItems = [];
let planOptionItems = [];
let comparisonItems = [];
let tripItems = [];
let preferenceItems = [];
let eventItems = [];
let recallItems = [];
let checkpointItems = [];
let memorySnapshot = null;
let selectedComparisonPlanIds = new Set();

marked.setOptions({
  gfm: true,
  breaks: true
});


function normalizeMarkdown(rawText) {
  // 在真正渲染前，先把模型常见的“不规范 Markdown”修正一下，
  // 这样像标题、分隔线、列表这些结构更容易被解析出来。
  let text = String(rawText || "");

  // 修正标题写法：###**标题** -> ### **标题**
  text = text.replace(/^(#{1,6})(\*\*|\S)/gm, (match, hashes, nextPart) => {
    if (nextPart.startsWith(" ")) {
      return match;
    }
    return `${hashes} ${nextPart}`;
  });

  // 修正标题强调写法：## **天气情况** -> ## 天气情况
  text = text.replace(/^(#{1,6})\s+\*\*(.*?)\*\*\s*$/gm, "$1 $2");

  // 修正分隔线写法：-- 或 —— 这种不标准写法统一转成 ---
  text = text.replace(/^\s*(--|——|—{2,})\s*$/gm, "---");

  // 修正列表写法：-**内容** -> - **内容**
  text = text.replace(/^(\s*[-*])(\*\*|\S)/gm, (match, bullet, nextPart) => {
    if (nextPart.startsWith(" ")) {
      return match;
    }
    return `${bullet} ${nextPart}`;
  });

  // 修正有序列表写法：1.**内容** -> 1. **内容**
  text = text.replace(/^(\s*\d+\.)((?!\s).)/gm, "$1 $2");

  // 清理孤立的强调标记，避免页面上残留 **、## 这类符号
  text = text.replace(/^\s*(\*\*|__)\s*$/gm, "");
  text = text.replace(/\n{3,}/g, "\n\n");

  return text;
}


function stripMarkdownForPreview(rawText) {
  let text = normalizeMarkdown(rawText);
  text = text.replace(/```[\s\S]*?```/g, " ");
  text = text.replace(/`([^`]*)`/g, "$1");
  text = text.replace(/!\[[^\]]*\]\([^)]+\)/g, " ");
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  text = text.replace(/^\s*#{1,6}\s*/gm, "");
  text = text.replace(/^\s*[-*+]\s*/gm, "");
  text = text.replace(/^\s*\d+\.\s*/gm, "");
  text = text.replace(/^\s*>\s*/gm, "");
  text = text.replace(/^\s*---+\s*$/gm, " ");
  text = text.replace(/[*_~|#>`]/g, " ");
  text = text.replace(/\s+/g, " ");
  return text.trim();
}


function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}


function autoResizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 180)}px`;
}


function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}


function closeHeaderActionMenu() {
  if (headerActionMenu?.open) {
    headerActionMenu.removeAttribute("open");
  }
}


function closeWorkspaceDrawer() {
  if (workspaceDrawerToggle?.open) {
    workspaceDrawerToggle.removeAttribute("open");
  }
}


function hideWelcomeCard() {
  welcomeCard.classList.add("hidden");
}


function showWelcomeCard() {
  welcomeCard.classList.remove("hidden");
}


function createMessageRow(role, text = "") {
  const row = document.createElement("article");
  row.className = `message-row ${role}`;

  if (role === "user") {
    row.innerHTML = `
      <div class="message-shell">
        <div class="message-bubble">
          <div class="plain-message">${escapeHtml(text)}</div>
        </div>
      </div>
      <div class="message-avatar">你</div>
    `;
    return { row };
  }

  row.innerHTML = `
    <div class="message-avatar">TA</div>
    <div class="message-shell">
      <div class="message-head">
        <div class="message-title">Travel Agent</div>
        <div class="phase-badge" data-role="phase">准备中</div>
      </div>
      <div class="tool-stream" data-role="tool-stream">
        <details class="tool-panel">
          <summary>工具执行记录</summary>
          <div class="tool-log" data-role="tool-log"></div>
        </details>
      </div>
      <div class="message-bubble">
        <div class="message-placeholder" data-role="placeholder">正在整理你的需求...</div>
        <div class="streaming-body hidden streaming-cursor" data-role="streaming"></div>
        <div class="markdown-body hidden" data-role="body"></div>
      </div>
    </div>
  `;

  return {
    row,
    phase: row.querySelector('[data-role="phase"]'),
    toolStream: row.querySelector('[data-role="tool-stream"]'),
    toolLog: row.querySelector('[data-role="tool-log"]'),
    placeholder: row.querySelector('[data-role="placeholder"]'),
    streaming: row.querySelector('[data-role="streaming"]'),
    body: row.querySelector('[data-role="body"]'),
    rawContent: "",
    streamScheduled: false,
    phaseState: "planning",
  };
}


function appendUserMessage(text) {
  const message = createMessageRow("user", text);
  messageList.appendChild(message.row);
  scrollToBottom();
}


function appendAssistantMessage() {
  const message = createMessageRow("assistant");
  messageList.appendChild(message.row);
  scrollToBottom();
  return message;
}


function appendHistoryAssistantMessage(text) {
  const message = appendAssistantMessage();
  message.rawContent = text || "";
  setPhaseState(message, "done");
  updatePhase(message, "已完成");
  finalizeAssistantMessage(message);
}


function formatSessionTime(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}


function updateActiveSessionTitle(title) {
  activeSessionTitle.textContent = title || "新对话";
}


function getSessionPreview(item) {
  const preview = item.latest_user_message || item.summary || "";
  const cleanPreview = stripMarkdownForPreview(preview);
  return cleanPreview
    ? cleanPreview.slice(0, 42)
    : "还没有消息，点击后可以继续完善这次旅行规划。";
}


function renderSessionList() {
  sessionList.innerHTML = "";

  if (!sessionItems.length) {
    sessionEmpty.classList.remove("hidden");
    return;
  }

  sessionEmpty.classList.add("hidden");

  sessionItems.forEach((item) => {
    const shell = document.createElement("article");
    shell.className = "session-card-shell";

    const isActive = item.id === currentSessionId;
    shell.innerHTML = `
      <button type="button" class="session-card ${isActive ? "is-active" : ""}" data-role="open">
        <div class="session-card-title-row">
          <div class="session-card-title">${escapeHtml(item.title || "新对话")}</div>
        </div>
        <div class="session-card-preview">${escapeHtml(getSessionPreview(item))}</div>
        <div class="session-card-meta">
          <span>${escapeHtml(formatSessionTime(item.last_message_at) || "刚刚创建")}</span>
          <span class="session-card-status">${escapeHtml(item.status || "active")}</span>
        </div>
      </button>
      <details class="session-card-menu">
        <summary aria-label="会话操作"></summary>
        <div class="session-card-menu-panel">
          <button type="button" class="session-menu-btn" data-action="open">打开会话</button>
          <button type="button" class="session-menu-btn" data-action="rename">重命名</button>
          <button type="button" class="session-menu-btn" data-action="archive">归档</button>
          <button type="button" class="session-menu-btn danger" data-action="delete">删除</button>
        </div>
      </details>
    `;

    const openButton = shell.querySelector('[data-role="open"]');
    const menu = shell.querySelector(".session-card-menu");

    openButton.addEventListener("click", async () => {
      await switchSession(item.id, item.title || "新对话");
    });

    menu.addEventListener("toggle", () => {
      if (menu.open) {
        closeSessionCardMenus(menu);
      }
    });

    shell.querySelectorAll(".session-menu-btn").forEach((menuButton) => {
      menuButton.addEventListener("click", async (event) => {
        event.stopPropagation();
        menu.removeAttribute("open");

        const action = menuButton.dataset.action;
        if (action === "open") {
          await switchSession(item.id, item.title || "新对话");
          return;
        }
        if (action === "rename") {
          await renameSessionById(item.id);
          return;
        }
        if (action === "archive") {
          await archiveSessionById(item.id);
          return;
        }
        if (action === "delete") {
          await deleteSessionById(item.id);
        }
      });
    });

    sessionList.appendChild(shell);
  });
}


function closeSessionCardMenus(exceptMenu = null) {
  document.querySelectorAll(".session-card-menu[open]").forEach((menu) => {
    if (menu !== exceptMenu) {
      menu.removeAttribute("open");
    }
  });
}


function findSessionItem(sessionId) {
  return sessionItems.find((item) => item.id === sessionId);
}


function getPlanOptionPreview(item) {
  const preview = item.summary || "";
  const cleanPreview = stripMarkdownForPreview(preview);
  return cleanPreview ? cleanPreview.slice(0, 84) : "当前方案还没有摘要内容。";
}


function renderPlanOptions() {
  planOptionList.innerHTML = "";
  selectedComparisonPlanIds = new Set(
    Array.from(selectedComparisonPlanIds).filter((id) =>
      planOptionItems.some((item) => item.id === id)
    )
  );

  if (!currentSessionId || !planOptionItems.length) {
    planOptionEmpty.classList.remove("hidden");
    return;
  }

  planOptionEmpty.classList.add("hidden");

  planOptionItems.forEach((item) => {
    const card = document.createElement("article");
    card.className = "plan-card";
    if (item.is_selected) {
      card.classList.add("is-active");
    }

    const destination = item.primary_destination || "目的地待补充";
    const totalDays = item.total_days ? `${item.total_days} 天` : "天数待补充";
    const updatedAt = formatSessionTime(item.updated_at) || "刚刚更新";

    const branchName = item.branch_name || item.title || "未命名分支";
    const branchDepth = Number.isFinite(item.branch_depth) ? item.branch_depth : 0;
    const versionNo = Number.isFinite(item.version_no) ? item.version_no : 1;
    const childCount = Number.isFinite(item.child_count) ? item.child_count : 0;
    const branchHint = branchDepth > 0 ? `派生分支 ${branchDepth}` : "根分支";
    const branchMeta = `${branchName} / ${branchHint} / v${versionNo}`;
    const branchChildren = childCount > 0 ? `已派生 ${childCount} 个子分支` : "尚未派生子分支";

    card.innerHTML = `
      <div class="plan-card-head">
        <h3 class="plan-card-title">${escapeHtml(item.title || "未命名方案")}</h3>
        <span class="plan-card-status">${escapeHtml(item.status || "draft")}</span>
      </div>
      <div class="plan-card-branch">
        <span class="plan-branch-badge">${escapeHtml(branchMeta)}</span>
        <span class="plan-branch-copy">${escapeHtml(branchChildren)}</span>
      </div>
      <div class="plan-card-meta">
        <span>${escapeHtml(destination)}</span>
        <span>${escapeHtml(totalDays)}</span>
        <span>${escapeHtml(updatedAt)}</span>
      </div>
      <p class="plan-card-summary">${escapeHtml(getPlanOptionPreview(item))}</p>
      <div class="plan-card-actions">
        <button type="button" data-role="compare">${selectedComparisonPlanIds.has(item.id) ? "已加入比较" : "加入比较"}</button>
        <button type="button" data-role="copy">复制版本</button>
        <button type="button" data-role="archive">归档</button>
        <button type="button" data-role="delete">删除</button>
        <button type="button" data-role="trip">生成行程</button>
        <button type="button" class="is-primary" data-role="activate">设为当前方案</button>
      </div>
    `;

    card
      .querySelector('[data-role="compare"]')
      .addEventListener("click", () => {
        if (selectedComparisonPlanIds.has(item.id)) {
          selectedComparisonPlanIds.delete(item.id);
        } else {
          selectedComparisonPlanIds.add(item.id);
        }
        renderPlanOptions();
      });

    card
      .querySelector('[data-role="copy"]')
      .addEventListener("click", async () => {
        await copyPlanOption(item.id);
      });

    card
      .querySelector('[data-role="archive"]')
      .addEventListener("click", async () => {
        await archivePlanOption(item.id);
      });

    card
      .querySelector('[data-role="delete"]')
      .addEventListener("click", async () => {
        await deletePlanOption(item.id);
      });

    card
      .querySelector('[data-role="trip"]')
      .addEventListener("click", async () => {
        await createTrip({ plan_option_id: item.id });
      });

    card
      .querySelector('[data-role="activate"]')
      .addEventListener("click", async () => {
        await activatePlanOption(item.id);
      });

    planOptionList.appendChild(card);
  });
}


function renderEmptyState(listElement, emptyElement, hasItems) {
  listElement.innerHTML = "";
  emptyElement.classList.toggle("hidden", hasItems);
}


function renderMemorySnapshot() {
  const summary = memorySnapshot?.summary || "当前还没有会话摘要。";
  const activePlan = memorySnapshot?.active_plan_summary || "还没有激活方案。";
  const activeComparison = memorySnapshot?.active_comparison_summary || "当前没有活跃比较。";

  sessionSummaryText.textContent = stripMarkdownForPreview(summary) || "当前还没有会话摘要。";
  activePlanSummaryText.textContent = stripMarkdownForPreview(activePlan) || "还没有激活方案。";
  comparisonSummaryText.textContent = stripMarkdownForPreview(activeComparison) || "当前没有活跃比较。";
}


function renderPreferenceItems() {
  renderEmptyState(preferenceList, preferenceEmpty, preferenceItems.length > 0);
  if (!preferenceItems.length) {
    return;
  }

  preferenceItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "mini-card";
    const label = item.value?.label || item.value?.value || JSON.stringify(item.value || {});
    node.innerHTML = `
      <div class="mini-card-title">${escapeHtml(`${item.category}.${item.key}`)}</div>
      <div class="mini-card-copy">${escapeHtml(String(label))}</div>
    `;
    preferenceList.appendChild(node);
  });
}


function renderComparisons() {
  renderEmptyState(comparisonList, comparisonEmpty, comparisonItems.length > 0);
  if (!comparisonItems.length) {
    return;
  }

  comparisonItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "mini-card";
    node.innerHTML = `
      <div class="mini-card-title">${escapeHtml(item.name || "方案比较")}</div>
      <div class="mini-card-copy">${escapeHtml(stripMarkdownForPreview(item.summary || "当前比较还没有摘要。"))}</div>
    `;
    comparisonList.appendChild(node);
  });
}


function renderTrips() {
  renderEmptyState(tripList, tripEmpty, tripItems.length > 0);
  if (!tripItems.length) {
    return;
  }

  tripItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "mini-card";
    node.innerHTML = `
      <div class="mini-card-title">${escapeHtml(item.title || "未命名行程")}</div>
      <div class="mini-card-copy">${escapeHtml(stripMarkdownForPreview(item.summary || "正式行程已创建。"))}</div>
      <div class="mini-card-meta">${escapeHtml(item.primary_destination || "目的地待补充")} · ${escapeHtml(item.total_days ? `${item.total_days} 天` : "天数待补充")}</div>
    `;
    tripList.appendChild(node);
  });
}


function renderCheckpoints() {
  renderEmptyState(checkpointList, checkpointEmpty, checkpointItems.length > 0);
  if (!checkpointItems.length) {
    return;
  }

  checkpointItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "mini-card";
    node.innerHTML = `
      <div class="mini-card-title">${escapeHtml(item.label || "未命名检查点")}</div>
      <div class="mini-card-meta">${escapeHtml(formatSessionTime(item.created_at) || "")}</div>
    `;
    checkpointList.appendChild(node);
  });
}


function renderEvents() {
  renderEmptyState(eventList, eventEmpty, eventItems.length > 0);
  if (!eventItems.length) {
    return;
  }

  eventItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "timeline-item";
    node.innerHTML = `
      <div class="timeline-title">${escapeHtml(item.event_type)}</div>
      <div class="timeline-copy">${escapeHtml(stripMarkdownForPreview(JSON.stringify(item.event_payload || {})))}</div>
      <div class="timeline-time">${escapeHtml(formatSessionTime(item.created_at) || "")}</div>
    `;
    eventList.appendChild(node);
  });
}


function renderRecalls() {
  renderEmptyState(recallList, recallEmpty, recallItems.length > 0);
  if (!recallItems.length) {
    return;
  }

  recallItems.forEach((item) => {
    const node = document.createElement("article");
    node.className = "timeline-item";
    node.innerHTML = `
      <div class="timeline-title">${escapeHtml(item.recall_type || "none")}</div>
      <div class="timeline-copy">${escapeHtml(stripMarkdownForPreview(item.summary || "暂无摘要"))}</div>
      <div class="timeline-time">${escapeHtml(formatSessionTime(item.created_at) || "")}</div>
    `;
    recallList.appendChild(node);
  });
}


function buildMiniTags(tags) {
  const visibleTags = tags.filter(Boolean);
  if (!visibleTags.length) {
    return "";
  }

  return `
    <div class="mini-card-tags">
      ${visibleTags
        .map((tag) => `<span class="mini-tag">${escapeHtml(String(tag))}</span>`)
        .join("")}
    </div>
  `;
}


function formatConfidenceLabel(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }

  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const percent = numeric <= 1 ? Math.round(numeric * 100) : Math.round(numeric);
    return `置信度 ${percent}%`;
  }

  return `置信度 ${String(value)}`;
}


function formatPreferenceSource(source) {
  const sourceMap = {
    user_explicit: "用户明确表达",
    user_inferred: "系统推断",
    session_override: "本轮会话覆盖",
    imported: "外部导入",
  };
  return sourceMap[source] || source || "未知来源";
}


function formatCheckpointScopeSummary(scope) {
  if (!scope || typeof scope !== "object") {
    return "恢复当前工作区快照";
  }

  const segments = [];
  if (scope.restores_plan_options) {
    segments.push("恢复方案树");
  }
  if (scope.restores_active_plan_pointer) {
    segments.push("恢复激活方案指针");
  }
  if (scope.restores_active_comparison_pointer) {
    segments.push("恢复比较指针");
  }
  if (scope.captures_session_summary_seed) {
    segments.push("保留摘要种子");
  }
  if (scope.does_not_restore_messages) {
    segments.push("消息流水不回滚");
  }
  if (scope.does_not_restore_comparison_rows) {
    segments.push("比较明细不回滚");
  }
  if (scope.does_not_restore_trip_rows) {
    segments.push("正式行程不回滚");
  }

  return segments.length ? segments.join(" · ") : "恢复当前工作区快照";
}


function renderMiniCard(container, html, className = "mini-card") {
  const node = document.createElement("article");
  node.className = className;
  node.innerHTML = html;
  container.appendChild(node);
}


function renderPreferenceItems() {
  const summaryText = stripMarkdownForPreview(memorySnapshot?.user_preference_summary || "");
  const hasItems = preferenceItems.length > 0 || Boolean(summaryText);
  renderEmptyState(preferenceList, preferenceEmpty, hasItems);
  if (!hasItems) {
    return;
  }

  if (summaryText) {
    renderMiniCard(
      preferenceList,
      `
        <div class="mini-card-title">偏好摘要注入</div>
        <div class="mini-card-copy timeline-copy-strong">${escapeHtml(summaryText)}</div>
        <div class="mini-card-meta">该摘要会随当前会话上下文一起注入，帮助模型延续用户偏好。</div>
      `,
      "mini-card mini-card-highlight"
    );
  }

  preferenceItems.forEach((item) => {
    const label = item.value?.label || item.value?.value || JSON.stringify(item.value || {});
    const meta = [formatPreferenceSource(item.source), formatConfidenceLabel(item.confidence)]
      .filter(Boolean)
      .join(" · ");
    renderMiniCard(
      preferenceList,
      `
        <div class="mini-card-title">${escapeHtml(`${item.category}.${item.key}`)}</div>
        <div class="mini-card-copy">${escapeHtml(String(label))}</div>
        ${buildMiniTags([
          item.source === "user_explicit" ? "长期稳定偏好" : "",
          item.category || "",
        ])}
        ${meta ? `<div class="mini-card-meta">${escapeHtml(meta)}</div>` : ""}
        ${
          item.updated_at
            ? `<div class="mini-card-meta">最近更新：${escapeHtml(formatSessionTime(item.updated_at) || "")}</div>`
            : ""
        }
      `
    );
  });
}


function renderCheckpoints() {
  renderEmptyState(checkpointList, checkpointEmpty, checkpointItems.length > 0);
  if (!checkpointItems.length) {
    return;
  }

  checkpointItems.forEach((item) => {
    renderMiniCard(
      checkpointList,
      `
        <div class="mini-card-title">${escapeHtml(item.label || "未命名检查点")}</div>
        <div class="mini-card-copy">${escapeHtml(formatCheckpointScopeSummary(item.snapshot_scope))}</div>
        ${buildMiniTags([
          item.summary_restore_mode ? `摘要恢复：${item.summary_restore_mode}` : "",
          item.active_plan_option_id ? "含激活方案指针" : "",
          item.active_comparison_id ? "含比较指针" : "",
        ])}
        <div class="mini-card-meta">${escapeHtml(formatSessionTime(item.created_at) || "")}</div>
      `
    );
  });
}


function renderRecalls() {
  renderEmptyState(recallList, recallEmpty, recallItems.length > 0);
  if (!recallItems.length) {
    return;
  }

  recallItems.forEach((item) => {
    const summary = stripMarkdownForPreview(item.summary || "暂无摘要");
    const decisionSummary = stripMarkdownForPreview(item.decision_summary || "");
    renderMiniCard(
      recallList,
      `
        <div class="timeline-title">${escapeHtml(item.recall_type || "none")}</div>
        <div class="timeline-copy">${escapeHtml(summary)}</div>
        ${
          decisionSummary
            ? `<div class="timeline-copy timeline-copy-strong">${escapeHtml(decisionSummary)}</div>`
            : ""
        }
        ${buildMiniTags([
          item.matched_record_type ? `命中 ${item.matched_record_type}` : "",
          item.matched_count ? `匹配 ${item.matched_count} 条` : "",
          formatConfidenceLabel(item.confidence),
        ])}
        <div class="timeline-time">${escapeHtml(formatSessionTime(item.created_at) || "")}</div>
      `,
      "timeline-item"
    );
  });
}


function updatePhase(message, label) {
  message.phase.textContent = label;
  if (!message.rawContent) {
    message.placeholder.textContent = label;
  }
}


function setPhaseState(message, state) {
  message.phaseState = state;
  message.phase.classList.remove("is-planning", "is-tooling", "is-answering", "is-done", "is-error");
  message.phase.classList.add(`is-${state}`);
}


function appendToolLog(message, content) {
  message.toolStream.classList.add("is-visible");
  const entry = document.createElement("div");
  entry.className = "tool-entry";
  entry.innerHTML = `
    <div class="tool-entry-label">Tool Output</div>
    <pre>${escapeHtml(content)}</pre>
  `;
  message.toolLog.appendChild(entry);
  scrollToBottom();
}


function scheduleStreamingRender(message) {
  if (message.streamScheduled) {
    return;
  }

  message.streamScheduled = true;
  requestAnimationFrame(() => {
    message.streamScheduled = false;
    message.placeholder.classList.add("hidden");
    message.streaming.classList.remove("hidden");
    message.body.classList.add("hidden");
    message.streaming.textContent = message.rawContent;
    scrollToBottom();
  });
}


function renderFinalMarkdown(message) {
  const normalized = normalizeMarkdown(message.rawContent || "");
  const html = DOMPurify.sanitize(marked.parse(normalized));
  message.body.innerHTML = html;
  message.body.querySelectorAll("a").forEach((link) => {
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  });
}


function finalizeAssistantMessage(message, hasError = false) {
  message.streaming.classList.remove("streaming-cursor");
  if (!message.rawContent) {
    message.placeholder.classList.remove("hidden");
    message.streaming.classList.add("hidden");
    message.body.classList.add("hidden");
    if (!hasError) {
      message.placeholder.textContent = "没有拿到有效回复，请稍后重试。";
    }
    return;
  }

  message.placeholder.classList.add("hidden");
  message.streaming.classList.add("hidden");
  message.body.classList.remove("hidden");
  renderFinalMarkdown(message);
}


function saveCurrentSessionId(sessionId) {
  currentSessionId = sessionId || "";
  if (currentSessionId) {
    localStorage.setItem(SESSION_STORAGE_KEY, currentSessionId);
  } else {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
  renderSessionList();
}


async function loadPlanOptions() {
  if (!currentSessionId) {
    planOptionItems = [];
    renderPlanOptions();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}${planOptionsPath}`);
    if (!response.ok) {
      throw new Error(`加载候选方案失败：${response.status}`);
    }

    const payload = await response.json();
    planOptionItems = Array.isArray(payload.items) ? payload.items : [];
    renderPlanOptions();
  } catch (_error) {
    planOptionItems = [];
    renderPlanOptions();
  }
}


async function renameSessionById(sessionId) {
  if (!sessionId) {
    return;
  }

  const current = findSessionItem(sessionId);
  const nextTitle = window.prompt("输入新的会话标题", current?.title || "新对话");
  if (nextTitle === null) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: nextTitle }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `重命名会话失败：${response.status}`);
    }

    const payload = await response.json();
    if (sessionId === currentSessionId) {
      updateActiveSessionTitle(payload.title || "新对话");
      await Promise.all([loadSessions(), refreshInsightPanels()]);
      return;
    }
    await loadSessions();
  } catch (error) {
    alert(error.message);
  }
}


async function archiveSessionById(sessionId) {
  if (!sessionId) {
    return;
  }
  if (!window.confirm("确认归档会话吗？归档后仍可在列表中查看。")) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}/archive`, {
      method: "PATCH",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `归档会话失败：${response.status}`);
    }

    if (sessionId === currentSessionId) {
      await Promise.all([loadSessions(), refreshInsightPanels()]);
      return;
    }
    await loadSessions();
  } catch (error) {
    alert(error.message);
  }
}


async function deleteSessionById(sessionId) {
  if (!sessionId) {
    return;
  }
  if (!window.confirm("确认删除会话吗？删除后无法恢复。")) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `删除会话失败：${response.status}`);
    }

    if (sessionId === currentSessionId) {
      clearConversation();
    }
    await loadSessions();
  } catch (error) {
    alert(error.message);
  }
}


async function renameCurrentSession() {
  await renameSessionById(currentSessionId);
}


async function archiveCurrentSession() {
  await archiveSessionById(currentSessionId);
}


async function deleteCurrentSession() {
  await deleteSessionById(currentSessionId);
}


async function createCheckpoint() {
  if (!currentSessionId) {
    return;
  }

  const label = window.prompt("输入检查点名称", "手动检查点");
  if (label === null) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/checkpoints`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ label }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `创建检查点失败：${response.status}`);
    }
    await Promise.all([loadCheckpoints(), loadSessionEvents()]);
  } catch (error) {
    alert(error.message);
  }
}


async function rewindLatestCheckpoint() {
  if (!currentSessionId) {
    return;
  }
  if (!checkpointItems.length) {
    alert("当前会话还没有可回退的检查点。");
    return;
  }
  const latest = checkpointItems[0];
  if (!window.confirm(`确认回退到最近检查点“${latest.label}”吗？`)) {
    return;
  }

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}/checkpoints/${latest.id}/rewind`,
      { method: "POST" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `回退检查点失败：${response.status}`);
    }
    await Promise.all([
      loadSessions(),
      loadSessionHistory(currentSessionId),
      loadPlanOptions(),
      refreshInsightPanels(),
    ]);
  } catch (error) {
    alert(error.message);
  }
}


async function loadMemorySnapshot() {
  if (!currentSessionId) {
    memorySnapshot = null;
    renderMemorySnapshot();
    renderPreferenceItems();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/memory`);
    if (!response.ok) {
      throw new Error(`加载会话记忆失败：${response.status}`);
    }
    memorySnapshot = await response.json();
  } catch (_error) {
    memorySnapshot = null;
  }
  renderMemorySnapshot();
  renderPreferenceItems();
}


async function loadComparisons() {
  if (!currentSessionId) {
    comparisonItems = [];
    renderComparisons();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/comparisons`);
    if (!response.ok) {
      throw new Error(`加载比较列表失败：${response.status}`);
    }
    const payload = await response.json();
    comparisonItems = Array.isArray(payload.items) ? payload.items : [];
  } catch (_error) {
    comparisonItems = [];
  }
  renderComparisons();
}


async function loadTrips() {
  if (!currentSessionId) {
    tripItems = [];
    renderTrips();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/trips`);
    if (!response.ok) {
      throw new Error(`加载正式行程失败：${response.status}`);
    }
    const payload = await response.json();
    tripItems = Array.isArray(payload.items) ? payload.items : [];
  } catch (_error) {
    tripItems = [];
  }
  renderTrips();
}


async function loadCheckpoints() {
  if (!currentSessionId) {
    checkpointItems = [];
    renderCheckpoints();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/checkpoints`);
    if (!response.ok) {
      throw new Error(`加载检查点失败：${response.status}`);
    }
    checkpointItems = await response.json();
  } catch (_error) {
    checkpointItems = [];
  }
  renderCheckpoints();
}


async function loadPreferences() {
  try {
    const response = await fetch("/preferences");
    if (!response.ok) {
      throw new Error(`加载偏好失败：${response.status}`);
    }
    preferenceItems = await response.json();
  } catch (_error) {
    preferenceItems = [];
  }
  renderPreferenceItems();
}


async function loadSessionEvents() {
  if (!currentSessionId) {
    eventItems = [];
    renderEvents();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/events`);
    if (!response.ok) {
      throw new Error(`加载事件失败：${response.status}`);
    }
    eventItems = await response.json();
  } catch (_error) {
    eventItems = [];
  }
  renderEvents();
}


async function loadRecallLogs() {
  if (!currentSessionId) {
    recallItems = [];
    renderRecalls();
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/recalls`);
    if (!response.ok) {
      throw new Error(`加载召回日志失败：${response.status}`);
    }
    recallItems = await response.json();
  } catch (_error) {
    recallItems = [];
  }
  renderRecalls();
}


async function refreshInsightPanels() {
  await Promise.all([
    loadMemorySnapshot(),
    loadComparisons(),
    loadTrips(),
    loadCheckpoints(),
    loadPreferences(),
    loadSessionEvents(),
    loadRecallLogs(),
  ]);
}


async function saveLatestReplyAsPlanOption() {
  if (!currentSessionId) {
    return;
  }

  savePlanBtn.disabled = true;
  savePlanBtn.textContent = "保存中...";

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}${planOptionsPath}/from-latest-message`,
      { method: "POST" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `保存方案失败：${response.status}`);
    }

    const payload = await response.json();
    await loadPlanOptions();
    if (payload.message) {
      savePlanBtn.textContent = payload.message;
      setTimeout(() => {
        savePlanBtn.textContent = "保存最新回复为方案";
      }, 1600);
    }
  } catch (error) {
    alert(error.message);
  } finally {
    savePlanBtn.disabled = false;
    if (savePlanBtn.textContent === "保存中...") {
      savePlanBtn.textContent = "保存最新回复为方案";
    }
  }
}


async function copyPlanOption(planOptionId) {
  if (!currentSessionId || !planOptionId) {
    return;
  }

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}${planOptionsPath}/${planOptionId}/copy`,
      { method: "POST" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `复制方案失败：${response.status}`);
    }
    await Promise.all([loadPlanOptions(), refreshInsightPanels()]);
  } catch (error) {
    alert(error.message);
  }
}


async function archivePlanOption(planOptionId) {
  if (!currentSessionId || !planOptionId) {
    return;
  }
  if (!window.confirm("确认归档这个候选方案吗？")) {
    return;
  }

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}${planOptionsPath}/${planOptionId}/archive`,
      { method: "PATCH" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `归档方案失败：${response.status}`);
    }
    selectedComparisonPlanIds.delete(planOptionId);
    await Promise.all([loadPlanOptions(), refreshInsightPanels()]);
  } catch (error) {
    alert(error.message);
  }
}


async function deletePlanOption(planOptionId) {
  if (!currentSessionId || !planOptionId) {
    return;
  }
  if (!window.confirm("确认删除这个候选方案吗？")) {
    return;
  }

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}${planOptionsPath}/${planOptionId}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `删除方案失败：${response.status}`);
    }
    selectedComparisonPlanIds.delete(planOptionId);
    await Promise.all([loadPlanOptions(), refreshInsightPanels()]);
  } catch (error) {
    alert(error.message);
  }
}


async function compareSelectedPlans() {
  if (!currentSessionId) {
    return;
  }

  const ids = Array.from(selectedComparisonPlanIds);
  if (ids.length < 2) {
    alert("请先勾选至少两个候选方案再发起比较。");
    return;
  }

  comparePlansBtn.disabled = true;
  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/comparisons`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        plan_option_ids: ids,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `创建比较失败：${response.status}`);
    }
    selectedComparisonPlanIds.clear();
    await Promise.all([loadComparisons(), loadMemorySnapshot(), loadSessionEvents(), loadPlanOptions()]);
  } catch (error) {
    alert(error.message);
  } finally {
    comparePlansBtn.disabled = false;
    renderPlanOptions();
  }
}


async function createTrip(payload = {}) {
  if (!currentSessionId) {
    return;
  }

  createTripBtn.disabled = true;
  try {
    const response = await fetch(`${sessionsEndpoint}/${currentSessionId}/trips`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `生成正式行程失败：${response.status}`);
    }
    await Promise.all([loadTrips(), loadPlanOptions(), loadMemorySnapshot(), loadSessionEvents(), loadComparisons()]);
  } catch (error) {
    alert(error.message);
  } finally {
    createTripBtn.disabled = false;
  }
}


async function activatePlanOption(planOptionId) {
  if (!currentSessionId || !planOptionId) {
    return;
  }

  try {
    const response = await fetch(
      `${sessionsEndpoint}/${currentSessionId}${planOptionsPath}/${planOptionId}/activate`,
      { method: "PATCH" }
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `激活方案失败：${response.status}`);
    }

    await loadPlanOptions();
  } catch (error) {
    alert(error.message);
  }
}


function parseSseBlock(block) {
  const lines = block.split("\n");
  let eventName = "message";
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  try {
    return {
      event: eventName,
      payload: JSON.parse(dataLines.join("\n"))
    };
  } catch (_error) {
    return null;
  }
}


async function streamReply(text) {
  const historyPayload = JSON.stringify(conversation);
  conversation.push({ role: "user", content: text });
  appendUserMessage(text);
  hideWelcomeCard();

  const assistantMessage = appendAssistantMessage();
  setPhaseState(assistantMessage, "planning");
  updatePhase(assistantMessage, "正在分析你的需求");

  sendBtn.disabled = true;

  const formData = new FormData();
  formData.append("message", text);
  formData.append("history", historyPayload);
  formData.append("session_id", currentSessionId);

  try {
    const response = await fetch(chatEndpoint, {
      method: "POST",
      body: formData,
    });

    if (!response.ok || !response.body) {
      throw new Error(`请求失败：${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let isFinished = false;

    const processEventBlock = (block) => {
      const event = parseSseBlock(block);
      if (!event) {
        return;
      }

      const { event: name, payload } = event;

      if (name === "phase") {
        const phaseValue = payload.value || "planning";
        setPhaseState(assistantMessage, phaseValue);
        updatePhase(assistantMessage, payload.label || "处理中");
      } else if (name === "intent") {
        activeIntentBadge.textContent = payload.action || "待命";
      } else if (name === "session") {
        saveCurrentSessionId(payload.session_id || "");
        updateActiveSessionTitle(payload.title || "新对话");
      } else if (name === "tool") {
        setPhaseState(assistantMessage, "tooling");
        updatePhase(assistantMessage, "正在调用旅行工具");
        appendToolLog(assistantMessage, payload.content || "");
      } else if (name === "token") {
        setPhaseState(assistantMessage, "answering");
        updatePhase(assistantMessage, "正在整理最终建议");
        assistantMessage.rawContent += payload.content || "";
        scheduleStreamingRender(assistantMessage);
      } else if (name === "error") {
        setPhaseState(assistantMessage, "error");
        updatePhase(assistantMessage, "发生错误");
        assistantMessage.placeholder.textContent = payload.message || "请求失败，请重试。";
        finalizeAssistantMessage(assistantMessage, true);
        conversation.push({
          role: "assistant",
          content: assistantMessage.rawContent || assistantMessage.placeholder.textContent,
        });
        isFinished = true;
      } else if (name === "done") {
        setPhaseState(assistantMessage, "done");
        updatePhase(assistantMessage, "已完成");
        finalizeAssistantMessage(assistantMessage);
        conversation.push({
          role: "assistant",
          content: assistantMessage.rawContent || assistantMessage.placeholder.textContent,
        });
        loadSessions();
        refreshInsightPanels();
        loadPlanOptions();
        isFinished = true;
      }
    };

    while (!isFinished) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      while (buffer.includes("\n\n")) {
        const boundary = buffer.indexOf("\n\n");
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        processEventBlock(block);
      }
    }

    if (!isFinished && buffer.trim()) {
      processEventBlock(buffer.trim());
    }

    if (!isFinished) {
      setPhaseState(assistantMessage, "done");
      updatePhase(assistantMessage, "已完成");
      finalizeAssistantMessage(assistantMessage);
      conversation.push({
        role: "assistant",
        content: assistantMessage.rawContent || assistantMessage.placeholder.textContent,
      });
      loadSessions();
      refreshInsightPanels();
      loadPlanOptions();
    }
  } catch (error) {
    setPhaseState(assistantMessage, "error");
    updatePhase(assistantMessage, "发生错误");
    assistantMessage.placeholder.textContent = `请求失败：${error.message}`;
    finalizeAssistantMessage(assistantMessage, true);
    conversation.push({
      role: "assistant",
      content: assistantMessage.rawContent || assistantMessage.placeholder.textContent,
    });
  } finally {
    sendBtn.disabled = false;
    messageInput.focus();
  }
}


function clearConversation() {
  conversation.length = 0;
  messageList.innerHTML = "";
  showWelcomeCard();
  saveCurrentSessionId("");
  updateActiveSessionTitle("新对话");
  planOptionItems = [];
  comparisonItems = [];
  tripItems = [];
  checkpointItems = [];
  eventItems = [];
  recallItems = [];
  memorySnapshot = null;
  selectedComparisonPlanIds.clear();
  activeIntentBadge.textContent = "待命";
  renderPlanOptions();
  renderMemorySnapshot();
  renderComparisons();
  renderTrips();
  renderCheckpoints();
  renderEvents();
  renderRecalls();
}


async function loadSessions() {
  try {
    const response = await fetch(sessionsEndpoint);
    if (!response.ok) {
      throw new Error(`加载会话列表失败：${response.status}`);
    }

    sessionItems = await response.json();
    renderSessionList();

    if (!currentSessionId && sessionItems.length > 0) {
      updateActiveSessionTitle("新对话");
    } else {
      const current = sessionItems.find((item) => item.id === currentSessionId);
      updateActiveSessionTitle(current?.title || "新对话");
    }
  } catch (_error) {
    sessionItems = [];
    renderSessionList();
  }
}


function resetConversationView() {
  conversation.length = 0;
  messageList.innerHTML = "";
  showWelcomeCard();
}


async function switchSession(sessionId, title = "新对话") {
  saveCurrentSessionId(sessionId);
  updateActiveSessionTitle(title);
  await Promise.all([loadSessionHistory(sessionId), loadPlanOptions(), refreshInsightPanels()]);
}


function startNewSession() {
  resetConversationView();
  saveCurrentSessionId("");
  updateActiveSessionTitle("新对话");
  planOptionItems = [];
  comparisonItems = [];
  tripItems = [];
  checkpointItems = [];
  eventItems = [];
  recallItems = [];
  memorySnapshot = null;
  selectedComparisonPlanIds.clear();
  activeIntentBadge.textContent = "待命";
  renderPlanOptions();
  renderMemorySnapshot();
  renderComparisons();
  renderTrips();
  renderCheckpoints();
  renderEvents();
  renderRecalls();
  messageInput.focus();
}


async function loadSessionHistory(sessionId = currentSessionId) {
  if (!sessionId) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}/messages`);
    if (!response.ok) {
      throw new Error(`加载会话失败：${response.status}`);
    }

    const payload = await response.json();
    resetConversationView();
    updateActiveSessionTitle(payload.title || "新对话");

    if (!Array.isArray(payload.messages) || !payload.messages.length) {
      return;
    }

    hideWelcomeCard();
    messageList.innerHTML = "";

    payload.messages.forEach((item) => {
      if (item.role === "user") {
        appendUserMessage(item.content || "");
        conversation.push({ role: "user", content: item.content || "" });
      } else if (item.role === "assistant") {
        appendHistoryAssistantMessage(item.content || "");
        conversation.push({ role: "assistant", content: item.content || "" });
      }
    });
  } catch (_error) {
    // 旧会话失效时直接清掉本地缓存，避免卡在坏状态。
    saveCurrentSessionId("");
    resetConversationView();
    updateActiveSessionTitle("新对话");
    await refreshInsightPanels();
  }
}


promptChips.forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt || "";
    autoResizeTextarea();
    messageInput.focus();
  });
});


document.addEventListener("click", (event) => {
  if (headerActionMenu?.open && !headerActionMenu.contains(event.target)) {
    closeHeaderActionMenu();
  }
  if (workspaceDrawerToggle?.open && !workspaceDrawerToggle.contains(event.target)) {
    closeWorkspaceDrawer();
  }
  if (!event.target.closest(".session-card-menu")) {
    closeSessionCardMenus();
  }
});


document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeHeaderActionMenu();
    closeWorkspaceDrawer();
    closeSessionCardMenus();
  }
});


messageInput.addEventListener("input", autoResizeTextarea);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composerForm.requestSubmit();
  }
});


composerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || sendBtn.disabled) {
    return;
  }

  messageInput.value = "";
  autoResizeTextarea();
  await streamReply(text);
});


clearBtn.addEventListener("click", clearConversation);
newSessionBtn.addEventListener("click", startNewSession);
refreshSessionsBtn.addEventListener("click", loadSessions);
savePlanBtn.addEventListener("click", saveLatestReplyAsPlanOption);
comparePlansBtn.addEventListener("click", compareSelectedPlans);
createTripBtn.addEventListener("click", () => createTrip());
createCheckpointBtn.addEventListener("click", createCheckpoint);
rewindCheckpointBtn.addEventListener("click", rewindLatestCheckpoint);
renameSessionBtn.addEventListener("click", renameCurrentSession);
archiveSessionBtn.addEventListener("click", archiveCurrentSession);
deleteSessionBtn.addEventListener("click", deleteCurrentSession);

[
  clearBtn,
  createCheckpointBtn,
  rewindCheckpointBtn,
  renameSessionBtn,
  archiveSessionBtn,
  deleteSessionBtn,
].forEach((button) => {
  button.addEventListener("click", closeHeaderActionMenu);
});

autoResizeTextarea();
loadSessions().then(() => Promise.all([loadSessionHistory(), loadPlanOptions(), refreshInsightPanels()]));
