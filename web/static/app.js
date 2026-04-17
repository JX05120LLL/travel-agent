const { chatEndpoint } = window.TRAVEL_AGENT_CONFIG;

const chatScroll = document.getElementById("chatScroll");
const messageList = document.getElementById("messageList");
const welcomeCard = document.getElementById("welcomeCard");
const composerForm = document.getElementById("composerForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const promptChips = document.querySelectorAll(".prompt-chip");

const conversation = [];

marked.setOptions({
  gfm: true,
  breaks: true
});


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


function hideWelcomeCard() {
  welcomeCard.classList.add("hidden");
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
  const html = DOMPurify.sanitize(marked.parse(message.rawContent || ""));
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
  welcomeCard.classList.remove("hidden");
}


promptChips.forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt || "";
    autoResizeTextarea();
    messageInput.focus();
  });
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
autoResizeTextarea();
