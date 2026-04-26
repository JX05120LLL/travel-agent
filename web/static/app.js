const { chatEndpoint, sessionsEndpoint, planOptionsPath } = window.TRAVEL_AGENT_CONFIG;
const SESSION_STORAGE_KEY = "travel_agent_session_id";
const markdownRenderer = window.TravelAgentMarkdown.createRenderer({
  markedLib: window.marked,
  domPurify: window.DOMPurify,
});

const chatScroll = document.getElementById("chatScroll");
const messageList = document.getElementById("messageList");
const welcomeCard = document.getElementById("welcomeCard");
const composerForm = document.getElementById("composerForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const newSessionBtn = document.getElementById("newSessionBtn");
const refreshSessionsBtn = document.getElementById("refreshSessionsBtn");
const currentTripPanel = document.getElementById("currentTripPanel");
const sessionList = document.getElementById("sessionList");
const sessionEmpty = document.getElementById("sessionEmpty");
const activeSessionTitle = document.getElementById("activeSessionTitle");
const savePlanBtn = document.getElementById("savePlanBtn");
const comparePlansBtn = document.getElementById("comparePlansBtn");
const createTripBtn = document.getElementById("createTripBtn");
const createCheckpointBtn = document.getElementById("createCheckpointBtn");
const rewindCheckpointBtn = document.getElementById("rewindCheckpointBtn");
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
const workspaceShell = document.getElementById("workspaceShell");
const sessionPanel = document.getElementById("sessionPanel");
const sidebarResizeHandle = document.getElementById("sidebarResizeHandle");
const sidebarCollapseBtn = document.getElementById("sidebarCollapseBtn");

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
let isReplyStreaming = false;
let tripPanelPendingRefresh = false;
let tripPanelBaselineSignature = "";
const SIDEBAR_WIDTH_STORAGE_KEY = "travel_agent_sidebar_width";
const SIDEBAR_COLLAPSED_STORAGE_KEY = "travel_agent_sidebar_collapsed";
const SIDEBAR_MIN_WIDTH = 260;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_DEFAULT_WIDTH = 296;
const SIDEBAR_COLLAPSED_WIDTH = 88;
const SIDEBAR_PEEK_OPEN_DELAY = 36;
const SIDEBAR_PEEK_CLOSE_DELAY = 140;
let sidebarPeekOpenTimer = null;
let sidebarPeekCloseTimer = null;

function normalizeMarkdown(rawText) {
  return markdownRenderer.normalizeMarkdown(rawText);
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


function compactPreviewText(rawText, maxLength = 140) {
  const text = stripMarkdownForPreview(rawText);
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trim()}…`;
}

function formatStayPriceSource(priceSource) {
  const value = (priceSource || "").trim().toLowerCase();
  if (!value) {
    return "";
  }
  if (value === "lowest_price" || value === "最低价") {
    return "价格来源：最低价";
  }
  if (value === "cost" || value === "人均价") {
    return "价格来源：人均价";
  }
  if (value === "高德未返回价格" || value === "unknown") {
    return "价格来源：高德未返回价格";
  }
  return "价格来源：" + priceSource;
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


function clampSidebarWidth(value) {
  return Math.max(SIDEBAR_MIN_WIDTH, Math.min(SIDEBAR_MAX_WIDTH, value));
}


function applySidebarWidth(width, { persist = true } = {}) {
  if (!workspaceShell) {
    return;
  }
  const nextWidth = clampSidebarWidth(Math.round(width || SIDEBAR_DEFAULT_WIDTH));
  workspaceShell.style.setProperty("--sidebar-width", `${nextWidth}px`);
  if (persist) {
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
  }
}


function clearSidebarPeekTimers() {
  if (sidebarPeekOpenTimer) {
    window.clearTimeout(sidebarPeekOpenTimer);
    sidebarPeekOpenTimer = null;
  }
  if (sidebarPeekCloseTimer) {
    window.clearTimeout(sidebarPeekCloseTimer);
    sidebarPeekCloseTimer = null;
  }
}


function setSidebarPeek(active) {
  if (!workspaceShell || !sessionPanel) {
    return;
  }
  const canPeek = workspaceShell.classList.contains("is-sidebar-collapsed")
    && !window.matchMedia("(max-width: 960px)").matches;
  const nextActive = Boolean(active) && canPeek;
  workspaceShell.classList.toggle("is-sidebar-peek", nextActive);
  sessionPanel.classList.toggle("is-peeking", nextActive);
}


function scheduleSidebarPeek(active, delay = active ? SIDEBAR_PEEK_OPEN_DELAY : SIDEBAR_PEEK_CLOSE_DELAY) {
  clearSidebarPeekTimers();
  const timer = window.setTimeout(() => {
    setSidebarPeek(active);
    if (active) {
      sidebarPeekOpenTimer = null;
    } else {
      sidebarPeekCloseTimer = null;
    }
  }, Math.max(0, delay));
  if (active) {
    sidebarPeekOpenTimer = timer;
  } else {
    sidebarPeekCloseTimer = timer;
  }
}


function setSidebarCollapsed(collapsed, { persist = true } = {}) {
  if (!workspaceShell || !sessionPanel) {
    return;
  }
  clearSidebarPeekTimers();
  if (!collapsed) {
    setSidebarPeek(false);
  }
  workspaceShell.classList.toggle("is-sidebar-collapsed", Boolean(collapsed));
  sessionPanel.classList.toggle("is-collapsed", Boolean(collapsed));
  if (sidebarCollapseBtn) {
    sidebarCollapseBtn.setAttribute("aria-label", collapsed ? "展开侧边栏" : "收起侧边栏");
    sidebarCollapseBtn.setAttribute("title", collapsed ? "展开侧边栏" : "收起侧边栏");
  }
  if (newSessionBtn) {
    newSessionBtn.textContent = collapsed ? "+" : "新对话";
    newSessionBtn.setAttribute("title", "新对话");
  }
  if (refreshSessionsBtn) {
    refreshSessionsBtn.textContent = collapsed ? "↻" : "刷新";
    refreshSessionsBtn.setAttribute("title", "刷新");
  }
  if (collapsed) {
    workspaceShell.style.setProperty("--sidebar-width", `${SIDEBAR_COLLAPSED_WIDTH}px`);
  } else {
    const storedWidth = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
    applySidebarWidth(Number.isFinite(storedWidth) ? storedWidth : SIDEBAR_DEFAULT_WIDTH, {
      persist: false,
    });
  }
  if (persist) {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
  }
}


function syncSidebarWidthFromViewport() {
  if (!workspaceShell) {
    return;
  }
  if (window.matchMedia("(max-width: 960px)").matches) {
    clearSidebarPeekTimers();
    setSidebarPeek(false);
    workspaceShell.style.removeProperty("--sidebar-width");
    workspaceShell.classList.remove("is-sidebar-collapsed");
    sessionPanel?.classList.remove("is-collapsed");
    return;
  }
  const isCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
  if (isCollapsed) {
    setSidebarCollapsed(true, { persist: false });
    return;
  }
  const storedWidth = Number(localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
  applySidebarWidth(Number.isFinite(storedWidth) ? storedWidth : SIDEBAR_DEFAULT_WIDTH, {
    persist: false,
  });
}


function initSidebarResize() {
  if (!workspaceShell || !sessionPanel || !sidebarResizeHandle) {
    return;
  }

  let isResizing = false;
  let startX = 0;
  let startWidth = SIDEBAR_DEFAULT_WIDTH;

  const stopResize = () => {
    if (!isResizing) {
      return;
    }
    isResizing = false;
    document.body.classList.remove("is-resizing-sidebar");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", stopResize);
  };

  const onPointerMove = (event) => {
    if (!isResizing) {
      return;
    }
    const delta = event.clientX - startX;
    applySidebarWidth(startWidth + delta);
  };

  sidebarResizeHandle.addEventListener("pointerdown", (event) => {
    if (window.matchMedia("(max-width: 960px)").matches) {
      return;
    }
    if (workspaceShell.classList.contains("is-sidebar-collapsed")) {
      setSidebarCollapsed(false);
    }
    isResizing = true;
    startX = event.clientX;
    startWidth = sessionPanel.getBoundingClientRect().width;
    document.body.classList.add("is-resizing-sidebar");
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    event.preventDefault();
  });

  sidebarResizeHandle.addEventListener("dblclick", () => {
    applySidebarWidth(SIDEBAR_DEFAULT_WIDTH);
  });

  sidebarCollapseBtn?.addEventListener("click", () => {
    const collapsed = workspaceShell.classList.contains("is-sidebar-collapsed");
    setSidebarCollapsed(!collapsed);
  });

  sessionPanel.addEventListener("pointerenter", () => {
    if (workspaceShell.classList.contains("is-sidebar-collapsed")) {
      scheduleSidebarPeek(true);
    }
  });

  sessionPanel.addEventListener("pointerleave", () => {
    if (workspaceShell.classList.contains("is-sidebar-collapsed")) {
      scheduleSidebarPeek(false);
    }
  });

  sessionPanel.addEventListener("focusin", () => {
    if (workspaceShell.classList.contains("is-sidebar-collapsed")) {
      clearSidebarPeekTimers();
      setSidebarPeek(true);
    }
  });

  sessionPanel.addEventListener("focusout", () => {
    if (!workspaceShell.classList.contains("is-sidebar-collapsed")) {
      return;
    }
    window.setTimeout(() => {
      if (!sessionPanel.contains(document.activeElement)) {
        scheduleSidebarPeek(false, 60);
      }
    }, 0);
  });

  window.addEventListener("resize", syncSidebarWidthFromViewport);
  syncSidebarWidthFromViewport();
}


function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}


function closeWorkspaceDrawer() {
  if (workspaceDrawerToggle?.open) {
    workspaceDrawerToggle.removeAttribute("open");
  }
}


function closeOpenToolPanels(target = null) {
  document.querySelectorAll(".tool-panel[open]").forEach((panel) => {
    if (target && panel.contains(target)) {
      return;
    }
    panel.removeAttribute("open");
  });
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
      <div class="message-avatar">我</div>
    `;
    return { row };
  }

  row.innerHTML = `
    <div class="message-avatar">TA</div>
    <div class="message-shell">
      <div class="message-head">
        <div class="message-title">旅行助手</div>
        <div class="phase-badge" data-role="phase">准备中</div>
      </div>
      <div class="tool-stream" data-role="tool-stream">
        <details class="tool-panel">
          <summary>
            <span class="tool-panel-summary-label">查看工具过程</span>
            <span class="tool-panel-summary-meta" data-role="tool-meta">0 条记录</span>
          </summary>
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
    toolMeta: row.querySelector('[data-role="tool-meta"]'),
    placeholder: row.querySelector('[data-role="placeholder"]'),
    streaming: row.querySelector('[data-role="streaming"]'),
    body: row.querySelector('[data-role="body"]'),
    rawContent: "",
    streamScheduled: false,
    phaseState: "planning",
    workspacePayload: null,
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


function appendHistoryAssistantMessage(text, metadata = {}) {
  const message = appendAssistantMessage();
  message.rawContent = text || "";
  message.workspacePayload = metadata?.workspace_sync || null;
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
    : "还没有消息，点开后可以继续完善这次旅行规划。";
}


function renderSessionList() {
  sessionList.innerHTML = "";

  if (!sessionItems.length) {
    sessionEmpty.classList.remove("hidden");
    return;
  }

  sessionEmpty.classList.add("hidden");

  const pinnedItems = sessionItems.filter((item) => item?.is_pinned);
  const regularItems = sessionItems.filter((item) => !item?.is_pinned);
  const groups = [
    { label: "置顶会话", items: pinnedItems },
    { label: "历史会话", items: regularItems },
  ].filter((group) => group.items.length > 0);

  groups.forEach((group) => {
    const groupLabel = document.createElement("div");
    groupLabel.className = "session-list-section-label";
    groupLabel.textContent = group.label;
    sessionList.appendChild(groupLabel);

    group.items.forEach((item) => {
      const shell = document.createElement("article");
      shell.className = "session-card-shell";

      const isActive = item.id === currentSessionId;
      const activeTrip = isActive ? getCurrentExportTrip() : null;
      const canExport = Boolean(isActive && currentSessionId && activeTrip?.id);
      const exportDisabledAttrs = canExport
        ? ""
        : ' disabled title="生成正式行程后可导出"';
      shell.innerHTML = `
        <button type="button" class="session-card ${isActive ? "is-active" : ""}" data-role="open">
          <div class="session-card-title-row">
            <div class="session-card-title">${escapeHtml(item.title || "新对话")}</div>
            <span class="session-card-active-dot ${isActive ? "is-visible" : ""}" aria-hidden="true"></span>
          </div>
          <div class="session-card-meta">
            ${item?.is_pinned ? '<span class="session-card-pin">已置顶</span>' : ""}
            <span>${escapeHtml(formatSessionTime(item.last_message_at) || "刚刚创建")}</span>
          </div>
        </button>
        <details class="session-card-menu">
          <summary aria-label="会话操作"></summary>
          <div class="session-card-menu-panel">
            <button type="button" class="session-menu-btn" data-action="pin">${
              item?.is_pinned ? "取消置顶" : "置顶"
            }</button>
            <button type="button" class="session-menu-btn" data-action="rename">重命名</button>
            ${
              isActive
                ? `
                  <button type="button" class="session-menu-btn" data-action="export-markdown"${exportDisabledAttrs}>导出 Markdown</button>
                  <button type="button" class="session-menu-btn" data-action="export-pdf"${exportDisabledAttrs}>导出 PDF</button>
                `
                : ""
            }
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
          if (action === "pin") {
            await toggleSessionPin(item.id, !item?.is_pinned);
            return;
          }
          if (action === "rename") {
            await renameSessionById(item.id);
            return;
          }
          if (action === "export-markdown") {
            try {
              await downloadTripExport("markdown");
            } catch (error) {
              window.alert(error.message || "导出 Markdown 失败");
            }
            return;
          }
          if (action === "export-pdf") {
            try {
              await downloadTripExport("pdf");
            } catch (error) {
              window.alert(error.message || "导出 PDF 失败");
            }
            return;
          }
          if (action === "delete") {
            await deleteSessionById(item.id);
          }
        });
      });

      sessionList.appendChild(shell);
    });
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


function getPrimaryComparisonItem() {
  if (!Array.isArray(comparisonItems) || !comparisonItems.length) {
    return null;
  }
  return comparisonItems.find((item) => item?.status === "active") || comparisonItems[0];
}


function getRecommendedPlanOptionId() {
  const comparison = getPrimaryComparisonItem();
  if (comparison?.recommended_option_id) {
    return comparison.recommended_option_id;
  }
  const active = planOptionItems.find((item) => item?.is_selected);
  return active?.id || null;
}


function getTripSourcePlanOptionIds() {
  return new Set(
    (Array.isArray(tripItems) ? tripItems : [])
      .map((item) => item?.source_plan_option_id)
      .filter(Boolean)
  );
}


function buildPlanOptionRole(item, recommendedPlanId, tripSourceIds) {
  if (item?.id && recommendedPlanId && item.id === recommendedPlanId) {
    return {
      label: "推荐方案",
      tone: "recommended",
      note: "当前系统优先展示并持续同步这个方案。",
    };
  }
  if (item?.is_selected) {
    return {
      label: "当前方案",
      tone: "active",
      note: "当前会话正在围绕这个方案继续细化。",
    };
  }
  if (item?.id && tripSourceIds.has(item.id)) {
    return {
      label: "已入正式行程",
      tone: "trip",
      note: "该方案已经同步进正式行程。",
    };
  }
  return {
    label: "备选方案",
    tone: "alternate",
    note: "系统会继续保留它，用于后续自动比较与切换。",
  };
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
  const recommendedPlanId = getRecommendedPlanOptionId();
  const tripSourceIds = getTripSourcePlanOptionIds();

  planOptionItems.forEach((item) => {
    const card = document.createElement("article");
    card.className = "plan-card";
    if (item.is_selected) {
      card.classList.add("is-active");
    }
    const role = buildPlanOptionRole(item, recommendedPlanId, tripSourceIds);
    card.classList.add(`plan-card-${role.tone}`);

    const destination = item.primary_destination || "目的地待补充";
    const totalDays = item.total_days ? String(item.total_days) + " 天" : "天数待补充";
    const updatedAt = formatSessionTime(item.updated_at) || "刚刚更新";

    const branchName = item.branch_name || item.title || "未命名分支";
    const branchDepth = Number.isFinite(item.branch_depth) ? item.branch_depth : 0;
    const versionNo = Number.isFinite(item.version_no) ? item.version_no : 1;
    const childCount = Number.isFinite(item.child_count) ? item.child_count : 0;
    const branchHint = branchDepth > 0 ? "派生分支 " + branchDepth : "根分支";
    const branchMeta = `${branchName} / ${branchHint} / v${versionNo}`;
    const branchChildren = childCount > 0 ? "已派生 " + childCount + " 个子分支" : "尚未派生子分支";

    card.innerHTML = `
      <div class="plan-card-head">
        <h3 class="plan-card-title">${escapeHtml(item.title || "未命名方案")}</h3>
        <span class="plan-card-role plan-card-role-${escapeHtml(role.tone)}">${escapeHtml(role.label)}</span>
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
      <div class="plan-card-note">${escapeHtml(role.note)}</div>
      ${renderStructuredCardStack(item, { title: "地图结果卡片", limit: 3 })}
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
  if (!listElement || !emptyElement) {
    return;
  }
  listElement.innerHTML = "";
  emptyElement.classList.toggle("hidden", hasItems);
}


function renderMemorySnapshot() {
  const summary = memorySnapshot?.summary || "当前还没有会话摘要。";
  const activePlan = memorySnapshot?.active_plan_summary || "还没有激活方案。";
  const activeComparison = memorySnapshot?.active_comparison_summary || "当前没有活跃比较。";

  if (sessionSummaryText) {
    sessionSummaryText.textContent = stripMarkdownForPreview(summary) || "当前还没有会话摘要。";
  }
  if (activePlanSummaryText) {
    activePlanSummaryText.textContent = stripMarkdownForPreview(activePlan) || "还没有激活方案。";
  }
  if (comparisonSummaryText) {
    comparisonSummaryText.textContent = stripMarkdownForPreview(activeComparison) || "当前没有活跃比较。";
  }
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
  renderCurrentTripPanel();
  if (!tripItems.length) {
    return;
  }

  tripItems.forEach((item) => {
    const hasItineraryDays = getTripItineraryDays(item).length > 0;
    renderMiniCard(
      tripList,
      `
        <div class="mini-card-title">${escapeHtml(item.title || "未命名行程")}</div>
        <div class="mini-card-copy">${escapeHtml(stripMarkdownForPreview(item.summary || "正式行程已创建。"))}</div>
        <div class="mini-card-meta">${escapeHtml(item.primary_destination || "目的地待补充")} 路 ${escapeHtml(item.total_days ? String(item.total_days) + " 天" : "天数待补充")}</div>
        ${hasItineraryDays ? "" : renderStructuredCardStack(item, { title: "行程卡片", limit: 3 })}
        ${renderTripItineraryMarkup(item)}
      `,
      "mini-card mini-card-trip"
    );
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
      <div class="mini-card-title">${escapeHtml(item.label || "鏈懡鍚嶆鏌ョ偣")}</div>
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
      <div class="timeline-copy">${escapeHtml(stripMarkdownForPreview(item.summary || "鏆傛棤鎽樿"))}</div>
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
    return `缃俊搴?${percent}%`;
  }

  return `缃俊搴?${String(value)}`;
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
    segments.push("恢复方案集");
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
    segments.push("消息记录不回滚");
  }
  if (scope.does_not_restore_comparison_rows) {
    segments.push("比较记录不回滚");
  }
  if (scope.does_not_restore_trip_rows) {
    segments.push("正式行程不回滚");
  }

  return segments.length ? segments.join(" 路 ") : "恢复当前工作区快照";
}


function renderMiniCard(container, html, className = "mini-card") {
  const node = document.createElement("article");
  node.className = className;
  node.innerHTML = html;
  container.appendChild(node);
}


function getStructuredCards(item) {
  if (!item?.structured_context || typeof item.structured_context !== "object") {
    return [];
  }

  const cards = [];
  const pushCards = (value) => {
    if (!Array.isArray(value)) {
      return;
    }
    value.forEach((card) => {
      if (card && typeof card === "object") {
        cards.push(card);
      }
    });
  };

  pushCards(item.structured_context.cards);
  Object.values(item.structured_context).forEach((section) => {
    if (section && typeof section === "object") {
      pushCards(section.cards);
    }
  });

  const deduped = new Map();
  cards.forEach((card) => {
    const key = [
      card.provider || "",
      card.type || "",
      card.title || "",
      card.summary || "",
    ].join("|");
    if (!deduped.has(key)) {
      deduped.set(key, card);
    }
  });
  return Array.from(deduped.values());
}


function formatStructuredCardType(type) {
  const labels = {
    route: "路线卡",
    spot_route: "串联卡",
    stay_recommendations: "住宿卡",
    food_recommendations: "美食卡",
    weather: "天气卡",
    poi_list: "点位卡",
    arrival_recommendation: "到达卡",
    budget_summary: "预算卡",
    travel_notes: "提醒卡",
    planning_assumptions: "说明卡",
  };
  return labels[type] || "信息卡";
}


function getStructuredCardVariant(type) {
  const variants = {
    route: "route",
    spot_route: "route",
    stay_recommendations: "stay",
    food_recommendations: "food",
    weather: "weather",
    poi_list: "poi",
    arrival_recommendation: "route",
    budget_summary: "budget",
    travel_notes: "generic",
    planning_assumptions: "generic",
  };
  return variants[type] || "generic";
}


function buildStructuredCardPresentation(card) {
  const type = card?.type || "generic";
  const data = card?.data && typeof card.data === "object" ? card.data : {};
  const fallbackSummary = stripMarkdownForPreview(card?.summary || "");

  if (type === "route") {
    return {
      title: card?.title || "路线规划",
      summary:
        fallbackSummary ||
        [data.origin, data.destination].filter(Boolean).join(" -> ") ||
        "已生成点到点路线规划。",
      meta: [data.distance_text, data.duration_text, data.ticket_cost_text || data.taxi_cost_text]
        .filter(Boolean)
        .join(" 路 "),
       tags: [data.mode, data.city, data.route_kind === "city_to_city" ? "跨城" : "点到点"],
    };
  }

  if (type === "spot_route") {
    return {
      title: card?.title || "景点串联路线",
      summary:
        fallbackSummary ||
        (Array.isArray(data.spot_sequence) && data.spot_sequence.length
          ? data.spot_sequence.slice(0, 4).join(" -> ")
          : "已生成景点串联路线。"),
      meta: [data.total_distance_text, data.total_duration_text, data.note]
        .filter(Boolean)
        .join(" 路 "),
      tags: [
        data.city,
        data.mode,
        Array.isArray(data.spot_sequence) && data.spot_sequence.length
          ? String(data.spot_sequence.length) + " 个点位"
          : "",
      ],
    };
  }

  if (type === "stay_recommendations") {
    const firstStay = Array.isArray(data.items) ? data.items[0] : null;
    return {
      title: card?.title || "住宿推荐",
      summary:
        fallbackSummary ||
        data.filter_summary ||
        (firstStay?.name ? "优先推荐 " + firstStay.name : "已生成住宿候选。"),
      meta: [
        firstStay?.name ? "优先项：" + firstStay.name : "",
        firstStay?.distance_text || "",
        firstStay?.budget_text || "",
        formatStayPriceSource(firstStay?.price_source),
      ]
        .filter(Boolean)
        .join(" 路 "),
      tags: [
        data.center,
        Number.isFinite(data.filtered_count) ? String(data.filtered_count) + " 个候选" : "",
        data.radius_text,
      ],
    };
  }

  if (type === "food_recommendations") {
    const firstFood = Array.isArray(data.items) ? data.items[0] : null;
    return {
      title: card?.title || "周边美食",
      summary:
        fallbackSummary ||
        (firstFood?.name ? "首推 " + firstFood.name : "已整理周边美食推荐。"),
      meta: [firstFood?.distance_text || "", firstFood?.address || ""]
        .filter(Boolean)
        .join(" 路 "),
      tags: [
        data.center,
        Number.isFinite(data.count) ? String(data.count) + " 个结果" : "",
        data.radius_text,
      ],
    };
  }

  if (type === "weather") {
    return {
      title: card?.title || "天气信息",
      summary: fallbackSummary || "已整理天气概览与出行建议。",
      meta: [data.city, data.current_text, data.forecast_range].filter(Boolean).join(" 路 "),
      tags: [data.city, data.extensions, Array.isArray(data.forecasts) ? String(data.forecasts.length) + " 天天气" : ""],
    };
  }

  if (type === "poi_list") {
    return {
      title: card?.title || "点位候选",
      summary:
        fallbackSummary ||
        [data.keywords, data.city].filter(Boolean).join(" 路 ") ||
        "已整理地图点位候选。",
      meta: [Number.isFinite(data.count) ? String(data.count) + " 个候选" : "", data.items?.[0]?.name || ""]
        .filter(Boolean)
        .join(" 路 "),
      tags: [data.city, data.keywords],
    };
  }

  if (type === "arrival_recommendation") {
    return {
      title: card?.title || "到达建议",
      summary:
        fallbackSummary ||
        [
          [data.origin_city, data.destination_city].filter(Boolean).join(" -> "),
          data.recommended_mode,
        ]
          .filter(Boolean)
          .join("，") ||
        "已整理跨城到达建议。",
      meta: [data.duration_text, data.price_text, data.booking_status].filter(Boolean).join(" 路 "),
      tags: [data.depart_date, data.recommended_mode],
    };
  }

  if (type === "budget_summary") {
    return {
      title: card?.title || "预算汇总",
      summary:
        fallbackSummary ||
        data.summary ||
        "已整理预算汇总。",
      meta: Array.isArray(data.items) ? data.items.slice(0, 2).join(" 路 ") : "",
      tags: [Array.isArray(data.items) ? String(data.items.length) + " 条预算说明" : ""],
    };
  }

  return {
    title: card?.title || "结构化信息",
    summary: fallbackSummary || "已写入结构化结果。",
    meta: "",
    tags: [card?.provider || ""],
  };
}


function renderStructuredCardMarkup(card) {
  const type = card?.type || "generic";
  const variant = getStructuredCardVariant(type);
  const presentation = buildStructuredCardPresentation(card);

  return `
    <article class="structured-mini-card structured-mini-card-${variant}">
      <div class="structured-mini-card-head">
        <span class="structured-mini-card-kicker">${escapeHtml(card?.provider || "structured")}</span>
        <span class="structured-mini-card-badge structured-mini-card-badge-${variant}">
          ${escapeHtml(formatStructuredCardType(type))}
        </span>
      </div>
      <div class="structured-mini-card-title">${escapeHtml(presentation.title)}</div>
      <div class="structured-mini-card-copy">${escapeHtml(presentation.summary)}</div>
      ${
        presentation.meta
          ? `<div class="structured-mini-card-meta">${escapeHtml(presentation.meta)}</div>`
          : ""
      }
      ${buildMiniTags(presentation.tags || [])}
    </article>
  `;
}


function renderStructuredCardStack(item, options = {}) {
  const cards = getStructuredCards(item);
  if (!cards.length) {
    return "";
  }

  const title = options.title || "结构化卡片";
  const visibleCards = cards.slice(0, options.limit || 3);
  const remainingCount = Math.max(cards.length - visibleCards.length, 0);

  return `
    <section class="structured-card-stack">
      <div class="structured-card-stack-head">
        <div class="structured-card-stack-title">${escapeHtml(title)}</div>
        <div class="structured-card-stack-count">${escapeHtml(String(cards.length) + " 张")}</div>
      </div>
      <div class="structured-card-grid">
        ${visibleCards.map((card) => renderStructuredCardMarkup(card)).join("")}
      </div>
      ${
        remainingCount > 0
          ? `<div class="structured-card-stack-more">${escapeHtml("还有 " + remainingCount + " 张卡片已写入结构化结果")}</div>`
          : ""
      }
    </section>
  `;
}


function buildTripDayDigest(day) {
  if (!day || typeof day !== "object") {
    return "";
  }
  const cleanSummary = stripMarkdownForPreview(day.summary || "");
  if (cleanSummary) {
    return cleanSummary;
  }
  if (day?.day_type === "arrival") {
    const firstPeriod = Array.isArray(day?.periods) ? day.periods[0] : null;
    const firstBlock = Array.isArray(firstPeriod?.blocks) ? firstPeriod.blocks[0] : null;
    return stripMarkdownForPreview(
      [firstBlock?.transport || "", firstBlock?.activity || "", firstBlock?.note || ""]
        .filter(Boolean)
        .join("，")
    );
  }

  const items = Array.isArray(day.items) ? day.items : [];
  const spotSequence = items.find((item) => item?.type === "spot_sequence");
  if (spotSequence && Array.isArray(spotSequence.spot_sequence) && spotSequence.spot_sequence.length) {
    return spotSequence.spot_sequence.join(" -> ");
  }

  const transitItems = items.filter((item) => item?.type === "transit");
  if (transitItems.length) {
    return transitItems
      .map((item) => [item?.from || "", item?.to || ""].filter(Boolean).join(" -> "))
      .filter(Boolean)
      .slice(0, 2)
      .join(" / ");
  }

  const structuredCard = items.find((item) =>
    ["route", "spot_route", "stay_recommendations", "food_recommendations"].includes(item?.type)
  );
  return stripMarkdownForPreview(structuredCard?.summary || "");
}


function renderTripDayDigestMarkup(day) {
  const digest = buildTripDayDigest(day) || "系统已写入当日安排，等待进一步细化。";
  const kicker = day?.day_type === "arrival"
    ? "Day 0 到达日"
    : `第 ${escapeHtml(String(day?.day_no || ""))} 天`;
  const title = day?.title || (day?.day_type === "arrival"
    ? "Day 0 到达日"
    : ("第 " + (day?.day_no || "") + " 天"));
  return `
    <article class="trip-day-digest-card">
      <div class="trip-day-digest-kicker">${kicker}</div>
      <div class="trip-day-digest-title">${escapeHtml(title)}</div>
      <div class="trip-day-digest-copy">${escapeHtml(digest)}</div>
      ${
        day?.city_name
          ? `<div class="trip-day-digest-meta">${escapeHtml(day.city_name)}</div>`
          : ""
      }
    </article>
  `;
}


function renderTripDigestGrid(item) {
  const days = getTripDisplayDays(item);
  if (!days.length) {
    return "";
  }

  return `
    <section class="trip-digest-grid-wrap">
      <div class="trip-section-head">
        <div class="trip-section-title">每日摘要</div>
        <div class="trip-section-copy">${escapeHtml("已生成 " + days.length + " 天安排")}</div>
      </div>
      <div class="trip-digest-grid">
        ${days.map((day) => renderTripDayDigestMarkup(day)).join("")}
      </div>
    </section>
  `;
}


function renderStructuredShowcase(item) {
  const cards = getStructuredCards(item);
  if (!cards.length) {
    return "";
  }

  const groups = [
    {
      title: "路线重点",
      types: ["route", "spot_route", "poi_list"],
    },
    {
      title: "住宿推荐",
      types: ["stay_recommendations"],
    },
    {
      title: "到达与预算",
      types: ["arrival_recommendation", "budget_summary", "travel_notes", "planning_assumptions"],
    },
    {
      title: "美食推荐",
      types: ["food_recommendations"],
    },
  ];

  const sections = groups
    .map((group) => {
      const matched = cards.filter((card) => group.types.includes(card?.type)).slice(0, 3);
      if (!matched.length) {
        return "";
      }
      return `
        <section class="trip-showcase-section">
          <div class="trip-section-head">
            <div class="trip-section-title">${escapeHtml(group.title)}</div>
            <div class="trip-section-copy">${escapeHtml(String(matched.length) + " 张卡片")}</div>
          </div>
          <div class="structured-card-grid">
            ${matched.map((card) => renderStructuredCardMarkup(card)).join("")}
          </div>
        </section>
      `;
    })
    .filter(Boolean)
    .join("");

  return sections ? `<section class="trip-showcase-stack">${sections}</section>` : "";
}


function renderWorkspaceSyncOverview(payload) {
  const recommendedTitle = payload?.recommended_plan_title || "当前主方案";
  const tripTitle = payload?.active_trip_title || "尚未生成正式行程";
  const alternateTitles = Array.isArray(payload?.alternate_plan_titles)
    ? payload.alternate_plan_titles.filter(Boolean)
    : [];
  const recommendationReasons = Array.isArray(payload?.recommendation_reasons)
    ? payload.recommendation_reasons.filter(Boolean)
    : [];
  const tripState = payload?.active_trip_id ? "正式 Trip 已生成" : "当前仅同步主方案";
  const syncState = payload?.auto_compared_options ? "系统已自动比较并推荐" : "当前按主方案继续输出";

  return `
    <section class="trip-decision-card">
      <div class="trip-section-head">
        <div class="trip-section-title">当前决策结果</div>
        <div class="trip-section-copy">${escapeHtml(syncState)}</div>
      </div>
      <div class="trip-decision-grid">
        <article class="trip-decision-block is-primary">
          <div class="trip-decision-label">推荐方案</div>
          <div class="trip-decision-value">${escapeHtml(recommendedTitle)}</div>
        </article>
        <article class="trip-decision-block">
          <div class="trip-decision-label">正式行程状态</div>
          <div class="trip-decision-value">${escapeHtml(tripState)}</div>
        </article>
        <article class="trip-decision-block">
          <div class="trip-decision-label">正式 Trip</div>
          <div class="trip-decision-value">${escapeHtml(tripTitle)}</div>
        </article>
        <article class="trip-decision-block">
          <div class="trip-decision-label">备选方案</div>
          <div class="trip-decision-value">${escapeHtml(alternateTitles.length ? alternateTitles.join(" / ") : "当前没有其他备选方案")}</div>
        </article>
      </div>
      ${
        recommendationReasons.length
          ? `<div class="trip-decision-reason">
              <div class="trip-decision-label">推荐理由</div>
              <ul class="trip-decision-reason-list">${recommendationReasons.map((reason) => `<li>${escapeHtml(String(reason))}</li>`).join("")}</ul>
            </div>`
          : ""
      }
    </section>
  `;
}


function renderTripHeroMarkup(item, payload) {
  const documentPayload = item?.delivery_payload || {};
  const destination = item?.primary_destination || "目的地待补充";
  const totalDays = item?.total_days ? String(item.total_days) + " 天" : "天数待补充";
  const summary = compactPreviewText(
    documentPayload?.overview?.summary || item?.summary || payload?.active_plan_summary || "",
    96
  );
  const heroBadges = [
    payload?.active_trip_id ? "正式行程已生成" : "当前主方案",
    payload?.trip_document_ready ? "成品行程单已生成" : "",
    item?.total_days ? `${item.total_days} 天安排` : "",
  ].filter(Boolean);
  const compactMeta = [destination, totalDays].filter(Boolean).join(" · ");

  return `
    <section class="trip-hero-card">
      <div class="trip-hero-main trip-hero-main-compact">
        <div class="trip-hero-title-row">
          <div class="trip-hero-title">${escapeHtml(item?.title || payload?.active_trip_title || "旅行方案")}</div>
          ${
            compactMeta
              ? `<div class="trip-hero-meta-inline">${escapeHtml(compactMeta)}</div>`
              : ""
          }
        </div>
        ${
          summary
            ? `<div class="trip-hero-copy">${escapeHtml(summary)}</div>`
            : ""
        }
        ${
          heroBadges.length
            ? `<div class="trip-hero-badges">${heroBadges.slice(0, 2).map((badge) => `<span class="trip-hero-badge">${escapeHtml(badge)}</span>`).join("")}</div>`
            : ""
        }
      </div>
    </section>
  `;
}


function renderTripDecisionMarkup(payload) {
  const recommendedPlanId = payload?.recommended_plan_option_id || payload?.active_plan_option_id || getRecommendedPlanOptionId();
  const recommendedPlan = planOptionItems.find((item) => item?.id === recommendedPlanId) || null;
  const alternateTitles = Array.isArray(payload?.alternate_plan_titles)
    ? payload.alternate_plan_titles.filter(Boolean)
    : planOptionItems
        .filter((item) => item?.id && item.id !== recommendedPlanId)
        .slice(0, 3)
        .map((item) => item.title || "未命名方案");
  const recommendationReasons = Array.isArray(payload?.recommendation_reasons)
    ? payload.recommendation_reasons.filter(Boolean)
    : [];
  const fallbackReasonText = stripMarkdownForPreview(
    payload?.active_comparison_summary ||
    payload?.active_plan_summary ||
    "系统已结合当前候选方案和会话上下文，保留当前推荐作为主方案。"
  );
  const officialNotice = payload?.official_booking_notice;

  return `
    <section class="trip-decision-card">
      <div class="trip-section-head">
        <div class="trip-section-title">推荐决策</div>
        <div class="trip-section-copy">${escapeHtml(payload?.auto_compared_options ? "系统已自动比较候选方案" : "当前按激活方案继续输出")}</div>
      </div>
      <div class="trip-decision-grid">
        <article class="trip-decision-block is-primary">
          <div class="trip-decision-label">推荐方案</div>
          <div class="trip-decision-value">${escapeHtml(
            payload?.recommended_plan_title || recommendedPlan?.title || payload?.active_trip_title || "当前推荐方案"
          )}</div>
        </article>
        <article class="trip-decision-block">
          <div class="trip-decision-label">备选方案</div>
          <div class="trip-decision-value">${escapeHtml(
            alternateTitles.length
              ? alternateTitles.join(" / ")
              : "当前没有其他备选方案"
          )}</div>
        </article>
      </div>
      <div class="trip-decision-reason">
        <div class="trip-decision-label">推荐理由</div>
        ${
          recommendationReasons.length
            ? `<ul class="trip-decision-reason-list">${recommendationReasons.map((reason) => `<li>${escapeHtml(String(reason))}</li>`).join("")}</ul>`
            : `<div class="trip-decision-copy">${escapeHtml(fallbackReasonText)}</div>`
        }
      </div>
      ${
        officialNotice?.notice
          ? `<div class="trip-decision-copy">${escapeHtml("官方提醒：" + officialNotice.notice)}</div>`
          : ""
      }
    </section>
  `;
}


function renderTripDocumentMarkup(item) {
  const markdown = item?.document_markdown || "";
  if (!markdown) {
    return "";
  }

  return `
    <section class="trip-itinerary-stack trip-itinerary-document">
      <div class="trip-itinerary-stack-head">
        <div class="trip-itinerary-stack-title">成品行程单</div>
        <div class="trip-itinerary-stack-count">${escapeHtml("可直接发送/导出")}</div>
      </div>
      <div class="message-bubble">
        <div class="markdown-body">${sanitizeMarkdown(markdown)}</div>
      </div>
    </section>
  `;
}


function getTripItineraryDays(item) {
  if (!Array.isArray(item?.itinerary_days)) {
    return [];
  }
  return item.itinerary_days.filter((day) => day && typeof day === "object");
}


function getTripDeliveryPayload(item) {
  return item?.delivery_payload && typeof item.delivery_payload === "object"
    ? item.delivery_payload
    : {};
}


function getTripDisplayDays(item) {
  const payload = getTripDeliveryPayload(item);
  if (Array.isArray(payload?.daily_itinerary) && payload.daily_itinerary.length) {
    return payload.daily_itinerary.filter((day) => day && typeof day === "object");
  }
  return getTripItineraryDays(item);
}


function getTripArrivalDay(item) {
  return getTripDisplayDays(item).find((day) => day?.day_type === "arrival") || null;
}


function getTripHeroRouteSummary(item) {
  const daySummaries = getTripDisplayDays(item)
    .filter((day) => day?.day_type !== "arrival")
    .map((day, index) => {
      const sequenceItem = Array.isArray(day?.items)
        ? day.items.find((entry) => entry?.type === "spot_sequence" && Array.isArray(entry?.spot_sequence) && entry.spot_sequence.length)
        : null;
      const rawSummary = sequenceItem?.spot_sequence?.filter(Boolean)?.join(" -> ")
        || stripMarkdownForPreview(day?.summary || "");
      if (!rawSummary) {
        return "";
      }
      return `第 ${day?.day_no || index + 1} 天 ${rawSummary}`;
    })
    .filter(Boolean)
    .slice(0, 3);

  return daySummaries.join(" · ");
}

function getTripTimelineItems(day) {
  if (!Array.isArray(day?.items)) {
    return [];
  }
  return day.items.filter((item) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    return item.type === "transit" || item.type === "spot_sequence";
  });
}


function getTripStructuredDayCards(day) {
  if (!Array.isArray(day?.items)) {
    return [];
  }
  return day.items.filter((item) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    return ["route", "spot_route", "stay_recommendations", "food_recommendations", "poi_list"].includes(
      item.type
    );
  });
}


function getTripRenderableDayItems(day) {
  if (!Array.isArray(day?.items)) {
    return [];
  }
  return day.items.filter((item) => item && typeof item === "object");
}


function renderTripNarrativeBlock(block) {
  const title = block?.title || "行程安排";
  const detailRows = [
    block?.transport ? ["交通", block.transport] : null,
    block?.activity ? ["玩法", block.activity] : null,
    block?.food ? ["美食", block.food] : null,
    block?.note ? ["说明", block.note] : null,
  ].filter(Boolean);

  return `
    <article class="trip-itinerary-item trip-itinerary-item-brief">
      <div class="trip-itinerary-item-head">
        <div class="trip-itinerary-item-title">${escapeHtml(String(title))}</div>
        <div class="trip-itinerary-item-badge">${escapeHtml(block?.badge || "安排")}</div>
      </div>
      ${detailRows.map(([label, value]) => `
        <div class="trip-itinerary-item-row">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(value))}</strong>
        </div>
      `).join("")}
    </article>
  `;
}


function renderTripSpotSequenceItem(item) {
  const spots = Array.isArray(item?.spot_sequence) ? item.spot_sequence.filter(Boolean) : [];
  const originalSpots = Array.isArray(item?.original_spot_sequence)
    ? item.original_spot_sequence.filter(Boolean)
    : [];
  if (!spots.length) {
    return "";
  }

  return `
    <article class="trip-itinerary-item trip-itinerary-item-sequence">
      <div class="trip-itinerary-item-head">
        <div class="trip-itinerary-item-title">景点顺序优化</div>
        <div class="trip-itinerary-item-badge">景点顺序</div>
      </div>
      <div class="trip-sequence-flow">
        ${spots.map((spot) => `<span class="trip-sequence-chip">${escapeHtml(String(spot))}</span>`).join("")}
      </div>
      ${
        item?.optimization_note
          ? `<div class="trip-itinerary-item-copy">${escapeHtml(String(item.optimization_note))}</div>`
          : ""
      }
      ${
        originalSpots.length
          ? `<div class="trip-itinerary-item-meta">原始顺序：${escapeHtml(originalSpots.join(" -> "))}</div>`
          : ""
      }
      ${
        [item?.total_distance_text, item?.total_duration_text].filter(Boolean).length
          ? `<div class="trip-itinerary-item-meta">${escapeHtml(
              [item?.total_distance_text, item?.total_duration_text].filter(Boolean).join(" 路 ")
            )}</div>`
          : ""
      }
    </article>
  `;
}


function renderTripTransitStep(step, index) {
  const instruction = step?.instruction || ("第 " + (index + 1) + " 步");
  const meta = [
    step?.line || "",
    step?.departure_stop && step?.arrival_stop
      ? `${step.departure_stop} -> ${step.arrival_stop}`
      : (step?.destination_name || ""),
    step?.distance_text || "",
    step?.duration_text || "",
    step?.ticket_cost_text || "",
  ].filter(Boolean);

  return `
    <li class="trip-transit-step">
      <div class="trip-transit-step-index">${index + 1}</div>
      <div class="trip-transit-step-body">
        <div class="trip-transit-step-copy">${escapeHtml(String(instruction))}</div>
        ${
          meta.length
            ? `<div class="trip-transit-step-meta">${escapeHtml(meta.join(" 路 "))}</div>`
            : ""
        }
      </div>
    </li>
  `;
}


function renderTripTransitItem(item) {
  const stepDetails = Array.isArray(item?.step_details)
    ? item.step_details.filter((step) => step && typeof step === "object")
    : [];
  const steps = stepDetails.length
    ? stepDetails
    : (Array.isArray(item?.steps)
        ? item.steps.filter(Boolean).map((instruction) => ({ instruction }))
        : []);

  const summaryMeta = [
    item?.mode || "",
    item?.distance_text || "",
    item?.duration_text || "",
    item?.ticket_cost_text || "",
    item?.walking_distance_text || "",
  ].filter(Boolean);

  if (!steps.length) {
    return `
      <article class="trip-itinerary-item trip-itinerary-item-transit">
        <div class="trip-itinerary-item-head">
          <div class="trip-itinerary-item-title">${escapeHtml(
            [item?.from || "起点", item?.to || "终点"].join(" -> ")
          )}</div>
          <div class="trip-itinerary-item-badge">交通</div>
        </div>
        ${
          summaryMeta.length
            ? `<div class="trip-itinerary-item-meta">${escapeHtml(summaryMeta.join(" 路 "))}</div>`
            : ""
        }
        <div class="trip-itinerary-item-copy">这段交通已写入行程，但还没有逐步说明。</div>
      </article>
    `;
  }

  return `
    <details class="trip-itinerary-item trip-itinerary-item-transit trip-itinerary-item-collapsible">
      <summary class="trip-itinerary-summary">
        <div class="trip-itinerary-summary-main">
          <div class="trip-itinerary-item-head">
            <div class="trip-itinerary-item-title">${escapeHtml(
              [item?.from || "起点", item?.to || "终点"].join(" -> ")
            )}</div>
            <div class="trip-itinerary-item-badge">交通</div>
          </div>
          ${
            summaryMeta.length
              ? `<div class="trip-itinerary-item-meta">${escapeHtml(summaryMeta.join(" 路 "))}</div>`
              : ""
          }
        </div>
        <div class="trip-itinerary-summary-toggle">${escapeHtml("展开 " + steps.length + " 步")}</div>
      </summary>
      <div class="trip-itinerary-detail">
        <ol class="trip-transit-step-list">${steps.map((step, index) => renderTripTransitStep(step, index)).join("")}</ol>
      </div>
    </details>
  `;
}


function renderTripTimelineItem(item) {
  if (item?.type === "spot_sequence") {
    return renderTripSpotSequenceItem(item);
  }
  if (item?.type === "transit") {
    return renderTripTransitItem(item);
  }
  return "";
}

function formatTripPeriodLabel(period) {
  const labels = {
    morning: "上午",
    afternoon: "下午",
    evening: "晚上",
  };
  return labels[period] || "未分段";
}


function renderTripPeriodItem(item) {
  if (item?.type === "spot_sequence" || item?.type === "transit") {
    return renderTripTimelineItem(item);
  }
  if (!item?.type && (item?.title || item?.transport || item?.activity || item?.food || item?.note)) {
    return renderTripNarrativeBlock(item);
  }
  return renderStructuredCardMarkup(item);
}


function renderTripDayPeriodGroup(period, items, options = {}) {
  const visibleItems = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!visibleItems.length) {
    return "";
  }
  const title = options?.label || formatTripPeriodLabel(period?.key || period);

  return `
    <section class="trip-day-period">
      <div class="trip-day-period-head">
        <div class="trip-day-period-title">${escapeHtml(title)}</div>
        <div class="trip-day-period-count">${escapeHtml(String(visibleItems.length) + " 项")}</div>
      </div>
      <div class="trip-day-period-grid">
        ${visibleItems.map((item) => renderTripPeriodItem(item)).join("")}
      </div>
    </section>
  `;
}


function renderTripDayMarkup(day) {
  let periodMarkup = "";
  if (Array.isArray(day?.periods) && day.periods.length) {
    periodMarkup = day.periods
      .map((period) => renderTripDayPeriodGroup(period, period?.blocks || [], { label: period?.label }))
      .filter(Boolean)
      .join("");
  } else {
    const renderableItems = getTripRenderableDayItems(day);
    const periodOrder = ["morning", "afternoon", "evening"];
    const groupedItems = {
      morning: [],
      afternoon: [],
      evening: [],
    };
    renderableItems.forEach((item) => {
      const period = periodOrder.includes(item?.time_period) ? item.time_period : "afternoon";
      groupedItems[period].push(item);
    });
    periodMarkup = periodOrder
      .map((period) => renderTripDayPeriodGroup(period, groupedItems[period]))
      .filter(Boolean)
      .join("");
  }

  const dayKicker = day?.day_type === "arrival"
    ? "Day 0 到达日"
    : `第 ${escapeHtml(String(day?.day_no || ""))} 天`;
  const dayTitle = day?.title || (day?.day_type === "arrival"
    ? "Day 0 到达日"
    : ("第 " + (day?.day_no || "") + " 天"));

  return `
    <section class="trip-day-card">
      <div class="trip-day-head">
        <div>
          <div class="trip-day-kicker">${dayKicker}</div>
          <div class="trip-day-title">${escapeHtml(dayTitle)}</div>
        </div>
        <div class="trip-day-city">${escapeHtml(day?.city_name || "目的地待补充")}</div>
      </div>
      ${
        day?.summary
          ? `<div class="trip-day-summary">${escapeHtml(String(day.summary))}</div>`
          : ""
      }
      ${
        periodMarkup
          ? `<div class="trip-day-period-list">${periodMarkup}</div>`
          : ""
      }
      ${
        !periodMarkup
          ? `<div class="trip-day-empty">这一天还没有可展开的行程卡片。</div>`
          : ""
      }
    </section>
  `;
}


function renderTripItineraryMarkup(item) {
  const days = getTripDisplayDays(item);
  if (!days.length) {
    return "";
  }
  const itineraryDayCount = days.filter((day) => day?.day_type !== "arrival").length;
  const arrivalDayCount = days.filter((day) => day?.day_type === "arrival").length;
  const countText = arrivalDayCount
    ? `${itineraryDayCount || 0} 天行程 + ${arrivalDayCount} 个到达日`
    : `${days.length} 天`;

  return `
    <section class="trip-itinerary-stack">
      <div class="trip-itinerary-stack-head">
        <div class="trip-itinerary-stack-title">每日行程时间线</div>
        <div class="trip-itinerary-stack-count">${escapeHtml(countText)}</div>
      </div>
      <div class="trip-itinerary-day-list">
        ${days.map((day) => renderTripDayMarkup(day)).join("")}
      </div>
    </section>
  `;
}


function renderTripArrivalSection(item) {
  const payload = getTripDeliveryPayload(item);
  const arrival = payload?.arrival || {};
  if (!arrival || typeof arrival !== "object" || !Object.keys(arrival).length) {
    return "";
  }

  const topCandidate = Array.isArray(arrival?.candidates)
    ? arrival.candidates.find((entry) => entry && typeof entry === "object")
    : null;
  const detailRows = [
    ["推荐方式", arrival.recommended_mode || "待补充"],
    ["推荐车次", topCandidate?.train_no || (arrival.ticket_status === "placeholder" ? "暂未获取到真实车次" : "待补充")],
    ["出发/到达", [topCandidate?.depart_station || arrival.origin_city || "", topCandidate?.arrive_station || arrival.destination_city || ""].filter(Boolean).join(" -> ") || "待补充"],
    ["发到时间", [topCandidate?.depart_time || "", topCandidate?.arrive_time || ""].filter(Boolean).join(" -> ") || "待补充"],
    ["预计耗时", arrival.duration_text || "待补充"],
    ["票价参考", topCandidate?.price_text || arrival.price_text || "待补充"],
    ["余票参考", topCandidate?.availability_text || (arrival.ticket_status === "placeholder" ? "暂未获取到真实余票" : "待补充")],
    ["数据来源", arrival.data_source || "unknown"],
    ["查询时间", arrival.fetched_at || "待补充"],
  ];
  const officialNotice = arrival?.official_notice?.notice || "车次、票价、余票与购票规则请以铁路12306官网/App为准。";

  return `
    <section class="trip-detail-section trip-arrival-section">
      <div class="trip-section-head">
        <div class="trip-section-title">到达方式</div>
        <div class="trip-section-copy">${escapeHtml(arrival.ticket_status === "placeholder" ? "当前为占位到达建议" : "已接入真实车次候选")}</div>
      </div>
      <div class="trip-detail-grid">
        ${detailRows.map(([label, value]) => `
          <article class="trip-detail-card">
            <div class="trip-detail-label">${escapeHtml(label)}</div>
            <div class="trip-detail-value">${escapeHtml(String(value || "待补充"))}</div>
          </article>
        `).join("")}
      </div>
      ${
        arrival?.summary
          ? `<div class="trip-detail-note">${escapeHtml(arrival.summary)}</div>`
          : ""
      }
      <div class="trip-detail-notice">${escapeHtml("12306 提醒：" + officialNotice)}</div>
    </section>
  `;
}


function renderTripMapPreviewSection(item) {
  const payload = getTripDeliveryPayload(item);
  const mapPreview = payload?.map_preview || {};
  if (!mapPreview || typeof mapPreview !== "object" || !Object.keys(mapPreview).length) {
    return "";
  }

  const markers = Array.isArray(mapPreview?.markers)
    ? mapPreview.markers.filter((entry) => entry && typeof entry === "object")
    : [];
  const links = [
    (mapPreview?.personal_map_open_url || mapPreview?.personal_map_url)
      ? `<a class="trip-map-link is-primary" href="${escapeHtml(mapPreview.personal_map_open_url || mapPreview.personal_map_url)}" target="_blank" rel="noreferrer">打开专属地图预览</a>`
      : "",
    (mapPreview?.personal_map_url && mapPreview?.personal_map_open_url && mapPreview.personal_map_url !== mapPreview.personal_map_open_url)
      ? `<a class="trip-map-link" href="${escapeHtml(mapPreview.personal_map_url)}" target="_blank" rel="noreferrer">手机端打开高德App</a>`
      : "",
    mapPreview?.official_map_url
      ? `<a class="trip-map-link" href="${escapeHtml(mapPreview.official_map_url)}" target="_blank" rel="noreferrer">打开高德地图</a>`
      : "",
    mapPreview?.navigation_url
      ? `<a class="trip-map-link" href="${escapeHtml(mapPreview.navigation_url)}" target="_blank" rel="noreferrer">导航前往</a>`
      : "",
    mapPreview?.taxi_url
      ? `<a class="trip-map-link" href="${escapeHtml(mapPreview.taxi_url)}" target="_blank" rel="noreferrer">打车路线</a>`
      : "",
  ].filter(Boolean);

  return `
    <section class="trip-detail-section trip-map-section">
      <div class="trip-section-head">
        <div class="trip-section-title">地图预览</div>
        <div class="trip-section-copy">${escapeHtml(mapPreview.provider_mode || "fallback_link")}</div>
      </div>
      <div class="trip-map-summary">
        <div class="trip-map-title">${escapeHtml(mapPreview.title || "行程地图预览")}</div>
        <div class="trip-map-meta">${escapeHtml([mapPreview.city, mapPreview.center, mapPreview.fetched_at].filter(Boolean).join(" · "))}</div>
      </div>
      ${
        markers.length
          ? `<div class="trip-map-marker-list">${markers.slice(0, 8).map((marker) => `
              <span class="trip-map-marker-chip">${escapeHtml(marker.name || marker.location || "点位")}</span>
            `).join("")}</div>`
          : ""
      }
      ${
        links.length
          ? `<div class="trip-map-links">${links.join("")}</div>`
          : ""
      }
      ${
        mapPreview?.degraded_reason
          ? `<div class="trip-detail-note">${escapeHtml("地图预览已降级：" + mapPreview.degraded_reason)}</div>`
          : ""
      }
    </section>
  `;
}


function renderCurrentTripPanel() {
  if (!currentTripPanel) {
    return;
  }
  const trip = getCurrentExportTrip();
  const currentSignature = getTripPanelSignature(trip);
  if (!trip || isReplyStreaming || !trip.document_markdown) {
    currentTripPanel.classList.add("hidden");
    currentTripPanel.innerHTML = "";
    return;
  }
  if (tripPanelPendingRefresh && currentSignature === tripPanelBaselineSignature) {
    currentTripPanel.classList.add("hidden");
    currentTripPanel.innerHTML = "";
    return;
  }
  if (tripPanelPendingRefresh && currentSignature !== tripPanelBaselineSignature) {
    tripPanelPendingRefresh = false;
    tripPanelBaselineSignature = currentSignature;
  }

  const payload = {
    active_trip_id: trip.id,
    active_trip_title: trip.title,
    trip_document_ready: Boolean(trip.document_markdown),
    recommendation_reasons: getTripDeliveryPayload(trip)?.recommendation_reasons?.items || [],
  };
  currentTripPanel.classList.remove("hidden");
  currentTripPanel.innerHTML = `
    <section class="current-trip-board">
      ${renderTripHeroMarkup(trip, payload)}
      ${renderTripItineraryMarkup(trip)}
      ${renderTripDocumentMarkup(trip)}
    </section>
  `;
}


async function hydrateAssistantWorkspace(message) {
  return;
}


async function hydrateTripItems(items, sessionId) {
  if (!sessionId || !Array.isArray(items) || !items.length) {
    return Array.isArray(items) ? items : [];
  }

  const hydratedItems = await Promise.all(
    items.map(async (item) => {
      if (!item?.id) {
        return item;
      }
      try {
        const response = await fetch(`${sessionsEndpoint}/${sessionId}/trips/${item.id}`);
        if (!response.ok) {
          throw new Error(`???????????${response.status}`);
        }
        const payload = await response.json();
        return {
          ...item,
          ...payload,
        };
      } catch (_error) {
        return item;
      }
    })
  );

  return hydratedItems;
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
        <div class="mini-card-title">??????</div>
        <div class="mini-card-copy timeline-copy-strong">${escapeHtml(summaryText)}</div>
        <div class="mini-card-meta">??????????????????????????????</div>
      `,
      "mini-card mini-card-highlight"
    );
  }

  preferenceItems.forEach((item) => {
    const label = item.value?.label || item.value?.value || JSON.stringify(item.value || {});
    const meta = [formatPreferenceSource(item.source), formatConfidenceLabel(item.confidence)]
      .filter(Boolean)
      .join(" 路 ");
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
          item.summary_restore_mode ? "摘要恢复：" + item.summary_restore_mode : "",
          item.active_plan_option_id ? "包含激活方案指针" : "",
          item.active_comparison_id ? "包含比较指针" : "",
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
          item.matched_count ? "匹配 " + item.matched_count + " 条" : "",
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
  const nextCount = Number(message.toolLog.dataset.count || "0") + 1;
  message.toolLog.dataset.count = String(nextCount);
  if (message.toolMeta) {
    message.toolMeta.textContent = `${nextCount} 条记录`;
  }
  const entry = document.createElement("div");
  entry.className = "tool-entry";
  entry.innerHTML = `
    <div class="tool-entry-label">工具调用</div>
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
  markdownRenderer.renderIntoElement(message.body, message.rawContent || "");
}


function sanitizeMarkdown(markdown) {
  return markdownRenderer.renderMarkdownHtml(markdown || "");
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
  if (!window.confirm("确认归档这个会话吗？归档后仍可在列表中查看。")) {
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


async function toggleSessionPin(sessionId, isPinned) {
  if (!sessionId) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}/pin`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ is_pinned: Boolean(isPinned) }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `更新会话置顶失败：${response.status}`);
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
  if (!window.confirm("确认删除这个会话吗？删除后无法恢复。")) {
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
    alert("当前没有可回退的检查点。");
    return;
  }
  const latest = checkpointItems[0];
  if (!window.confirm('确认回退到最近检查点 "' + latest.label + '" 吗？')) {
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
    updateExportButtonsState();
    return;
  }

  try {
    const sessionId = currentSessionId;
    const response = await fetch(`${sessionsEndpoint}/${sessionId}/trips`);
    if (!response.ok) {
      throw new Error(`加载正式行程失败：${response.status}`);
    }
    const payload = await response.json();
    const summaryItems = Array.isArray(payload.items) ? payload.items : [];
    tripItems = await hydrateTripItems(summaryItems, sessionId);
  } catch (_error) {
    tripItems = [];
  }
  renderTrips();
  updateExportButtonsState();
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
  if (!currentSessionId || !savePlanBtn) {
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
  if (!currentSessionId || !comparePlansBtn) {
    return;
  }

  const ids = Array.from(selectedComparisonPlanIds);
  if (ids.length < 2) {
    alert("请至少选择两个候选方案再发起比较。");
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
  if (!currentSessionId || !createTripBtn) {
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
  tripPanelBaselineSignature = getTripPanelSignature(getCurrentExportTrip());
  tripPanelPendingRefresh = true;
  isReplyStreaming = true;
  renderCurrentTripPanel();

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
        if (activeIntentBadge) {
          activeIntentBadge.textContent = payload.action || "待命";
        }
      } else if (name === "session") {
        saveCurrentSessionId(payload.session_id || "");
        updateActiveSessionTitle(payload.title || "新对话");
      } else if (name === "tool") {
        setPhaseState(assistantMessage, "tooling");
        updatePhase(assistantMessage, "工具处理中");
        appendToolLog(assistantMessage, payload.content || "");
      } else if (name === "workspace") {
        assistantMessage.workspacePayload = payload || null;
      } else if (name === "token") {
        setPhaseState(assistantMessage, "answering");
        updatePhase(assistantMessage, "正在整理最终方案");
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
        isReplyStreaming = false;
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
      isReplyStreaming = false;
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
    isReplyStreaming = false;
  } finally {
    isReplyStreaming = false;
    sendBtn.disabled = false;
    messageInput.focus();
  }
}


function clearConversation() {
  conversation.length = 0;
  messageList.innerHTML = "";
  tripPanelPendingRefresh = false;
  tripPanelBaselineSignature = "";
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
  if (activeIntentBadge) {
    activeIntentBadge.textContent = "待命";
  }
  renderPlanOptions();
  renderMemorySnapshot();
  renderComparisons();
  renderTrips();
  renderCheckpoints();
  renderEvents();
  renderRecalls();
  updateExportButtonsState();
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
  tripPanelPendingRefresh = false;
  tripPanelBaselineSignature = "";
  showWelcomeCard();
}


async function switchSession(sessionId, title = "新对话") {
  saveCurrentSessionId(sessionId);
  updateActiveSessionTitle(title);
  tripPanelPendingRefresh = false;
  tripPanelBaselineSignature = "";
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
  if (activeIntentBadge) {
    activeIntentBadge.textContent = "待命";
  }
  renderPlanOptions();
  renderMemorySnapshot();
  renderComparisons();
  renderTrips();
  renderCheckpoints();
  renderEvents();
  renderRecalls();
  updateExportButtonsState();
  messageInput.focus();
}


async function loadSessionHistory(sessionId = currentSessionId) {
  if (!sessionId) {
    return;
  }

  try {
    const response = await fetch(`${sessionsEndpoint}/${sessionId}/messages`);
    if (!response.ok) {
      throw new Error(`加载会话消息失败：${response.status}`);
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
        appendHistoryAssistantMessage(item.content || "", item.metadata || {});
        conversation.push({ role: "assistant", content: item.content || "" });
      }
    });
    updateExportButtonsState();
  } catch (_error) {
    // 旧会话失效时直接清空本地缓存，避免页面卡在坏状态。
    saveCurrentSessionId("");
    resetConversationView();
    updateActiveSessionTitle("新对话");
    await refreshInsightPanels();
    updateExportButtonsState();
  }
}


function getCurrentExportTrip() {
  if (!Array.isArray(tripItems) || !tripItems.length) {
    return null;
  }
  return tripItems.find((item) => item?.status !== "archived") || tripItems[0] || null;
}


function getTripPanelSignature(trip) {
  if (!trip || typeof trip !== "object") {
    return "";
  }
  return [
    trip.id || "",
    trip.updated_at || "",
    trip.document_markdown ? "doc" : "nodoc",
  ].join("::");
}


function updateExportButtonsState() {
  if (Array.isArray(sessionItems) && sessionItems.length && sessionList) {
    renderSessionList();
  }
}


function extractDownloadFilename(disposition, fallbackName) {
  const value = disposition || "";
  const utf8Match = value.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch (_error) {
      // ignore malformed filename*
    }
  }
  const match = value.match(/filename=\"?([^\";]+)\"?/i);
  return match?.[1] || fallbackName;
}


async function downloadTripExport(format) {
  const trip = getCurrentExportTrip();
  if (!currentSessionId || !trip?.id) {
    return;
  }

  const response = await fetch(
    `${sessionsEndpoint}/${currentSessionId}/trips/${trip.id}/export/${format}`
  );
  if (!response.ok) {
    let message = `导出失败：${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (_error) {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const fallbackName = format === "pdf" ? "trip-document.pdf" : "trip-document.md";
  const filename = extractDownloadFilename(
    response.headers.get("content-disposition"),
    fallbackName,
  );
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}


promptChips.forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt || "";
    autoResizeTextarea();
    messageInput.focus();
  });
});


document.addEventListener("click", (event) => {
  if (workspaceDrawerToggle?.open && !workspaceDrawerToggle.contains(event.target)) {
    closeWorkspaceDrawer();
  }
  if (!event.target.closest(".session-card-menu")) {
    closeSessionCardMenus();
  }
  if (workspaceShell?.classList.contains("is-sidebar-collapsed")
    && workspaceShell.classList.contains("is-sidebar-peek")
    && sessionPanel
    && !sessionPanel.contains(event.target)) {
    clearSidebarPeekTimers();
    setSidebarPeek(false);
  }
  closeOpenToolPanels(event.target);
});


document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeHeaderActionMenu();
    closeWorkspaceDrawer();
    closeSessionCardMenus();
    clearSidebarPeekTimers();
    setSidebarPeek(false);
    closeOpenToolPanels();
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


newSessionBtn?.addEventListener("click", startNewSession);
refreshSessionsBtn?.addEventListener("click", loadSessions);
if (savePlanBtn) {
  savePlanBtn.addEventListener("click", saveLatestReplyAsPlanOption);
}
if (comparePlansBtn) {
  comparePlansBtn.addEventListener("click", compareSelectedPlans);
}
if (createTripBtn) {
  createTripBtn.addEventListener("click", () => createTrip());
}
createCheckpointBtn?.addEventListener("click", createCheckpoint);
rewindCheckpointBtn?.addEventListener("click", rewindLatestCheckpoint);

autoResizeTextarea();
updateExportButtonsState();
initSidebarResize();
loadSessions().then(() => Promise.all([loadSessionHistory(), loadPlanOptions(), refreshInsightPanels()]));


