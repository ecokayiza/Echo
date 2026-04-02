const STORAGE_KEYS = {
  sessionId: "eco-rag.session-id",
  systemPrompt: "eco-rag.system-prompt",
  modelSettings: "eco-rag.model-settings",
};

const DEFAULT_SYSTEM_PROMPT =
  "You are the chat assistant for Eco_RAG. Be clear, grounded, and concise. If you are unsure, say so.";

const elements = {
  composer: document.querySelector("#composer"),
  cacheHitTokens: document.querySelector("#cacheHitTokens"),
  contentTokens: document.querySelector("#contentTokens"),
  deleteSessionButton: document.querySelector("#deleteSessionButton"),
  liveLabel: document.querySelector("#liveLabel"),
  messageInput: document.querySelector("#messageInput"),
  messages: document.querySelector("#messages"),
  modelName: document.querySelector("#modelName"),
  applySystemPromptButton: document.querySelector("#applySystemPromptButton"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  baseUrlInput: document.querySelector("#baseUrlInput"),
  newSessionButton: document.querySelector("#newSessionButton"),
  providerInput: document.querySelector("#providerInput"),
  promptTokens: document.querySelector("#promptTokens"),
  renameSessionButton: document.querySelector("#renameSessionButton"),
  saveModelSettingsButton: document.querySelector("#saveModelSettingsButton"),
  sendButton: document.querySelector("#sendButton"),
  sessionId: document.querySelector("#sessionId"),
  sessionList: document.querySelector("#sessionList"),
  statusText: document.querySelector("#statusText"),
  systemPrompt: document.querySelector("#systemPrompt"),
  temperatureInput: document.querySelector("#temperatureInput"),
  totalTokens: document.querySelector("#totalTokens"),
  activeSessionTitle: document.querySelector("#activeSessionTitle"),
  modelInput: document.querySelector("#modelInput"),
};

const state = {
  busy: false,
  health: null,
  meta: null,
  messages: [],
  sessions: [],
  sessionId: localStorage.getItem(STORAGE_KEYS.sessionId),
};

elements.systemPrompt.value = localStorage.getItem(STORAGE_KEYS.systemPrompt) ?? DEFAULT_SYSTEM_PROMPT;

boot().catch((error) => {
  setStatus(`Startup failed: ${error.message}`, true);
});

elements.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendMessage();
});

elements.messageInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter" && event.ctrlKey) {
    event.preventDefault();
    await sendMessage();
  }
});

elements.newSessionButton.addEventListener("click", async () => {
  await createSession();
});

elements.renameSessionButton.addEventListener("click", async () => {
  if (!state.sessionId || state.busy) {
    return;
  }

  const current = activeSession();
  const nextTitle = window.prompt("Rename session", current?.title || "New Session");
  if (nextTitle === null) {
    return;
  }

  await withBusy("Renaming session...", async () => {
    const session = await fetchJson(`/api/sessions/${encodeURIComponent(state.sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: nextTitle }),
    });
    mergeSession(session);
    renderSessions();
    updateSessionMeta();
    setStatus("Session renamed.");
  });
});

elements.deleteSessionButton.addEventListener("click", async () => {
  if (!state.sessionId || state.busy) {
    return;
  }

  const current = activeSession();
  const confirmed = window.confirm(`Delete session "${current?.title || state.sessionId}"?`);
  if (!confirmed) {
    return;
  }

  await withBusy("Deleting session...", async () => {
    await fetchJson(`/api/sessions/${encodeURIComponent(state.sessionId)}`, { method: "DELETE" });
    state.sessions = state.sessions.filter((session) => session.session_id !== state.sessionId);

    if (state.sessions.length) {
      await selectSession(state.sessions[0].session_id);
    } else {
      await createSession();
    }
    setStatus("Session deleted.");
  });
});

elements.systemPrompt.addEventListener("input", () => {
  setStatus("System prompt changed. Click Apply Prompt to use it.");
});

elements.applySystemPromptButton.addEventListener("click", async () => {
  const content = elements.systemPrompt.value;
  if (!state.sessionId || state.busy) {
    return;
  }

  await withBusy("Updating system prompt...", async () => {
    const data = await fetchJson(`/api/sessions/${encodeURIComponent(state.sessionId)}/system-prompt`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content.trim() || null }),
    });
    localStorage.setItem(STORAGE_KEYS.systemPrompt, elements.systemPrompt.value);
    applySessionState(data);
    await loadSessions();
    setStatus("System prompt updated.");
  }, async (error) => {
    syncSystemPromptFromMessages();
    setStatus(error.message, true, "Error");
  });
});

elements.saveModelSettingsButton.addEventListener("click", () => {
  persistModelSettings();
  updateModelName();
  setStatus("Model settings saved locally.");
});

for (const input of [
  elements.providerInput,
  elements.modelInput,
  elements.baseUrlInput,
  elements.apiKeyInput,
  elements.temperatureInput,
]) {
  input.addEventListener("input", () => {
    updateModelName();
    setStatus("Model settings changed. Click Save to persist them.");
  });
}

elements.sessionList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-session-id]");
  if (!button || state.busy) {
    return;
  }
  await selectSession(button.dataset.sessionId);
});

elements.messages.addEventListener("click", async (event) => {
  const actionButton = event.target.closest("[data-action]");
  if (!actionButton || state.busy) {
    return;
  }

  const { action, messageId } = actionButton.dataset;
  const message = state.messages.find((item) => item.id === messageId);
  if (!message) {
    return;
  }

  if (action === "edit") {
    const updated = window.prompt("Edit message", message.content);
    if (updated === null) {
      return;
    }
    await mutateMessage(
      `Editing ${message.role} message...`,
      `/api/sessions/${encodeURIComponent(state.sessionId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: updated }),
      },
      "Message updated."
    );
    return;
  }

  if (action === "delete") {
    const confirmed = window.confirm("Delete this message and the turns after it?");
    if (!confirmed) {
      return;
    }
    await mutateMessage(
      "Deleting message...",
      `/api/sessions/${encodeURIComponent(state.sessionId)}/messages/${encodeURIComponent(messageId)}`,
      { method: "DELETE" },
      "Message deleted. Later turns were trimmed."
    );
    return;
  }

  if (action === "rollback") {
    const confirmed = window.confirm("Rollback the session to this message?");
    if (!confirmed) {
      return;
    }
    await mutateMessage(
      "Rolling back session...",
      `/api/sessions/${encodeURIComponent(state.sessionId)}/messages/${encodeURIComponent(messageId)}/rollback`,
      { method: "POST" },
      "Rolled back to the selected message."
    );
    return;
  }

  if (action === "regenerate") {
    await streamRegeneration(messageId);
  }
});

async function boot() {
  await loadMeta();
  await loadHealth();
  await loadSessions();

  if (!state.sessions.length) {
    await createSession();
    return;
  }

  const sessionExists = state.sessions.some((session) => session.session_id === state.sessionId);
  const targetSessionId = sessionExists ? state.sessionId : state.sessions[0].session_id;
  await selectSession(targetSessionId);
  setStatus("Ready");
}

async function loadHealth() {
  state.health = await fetchJson("/api/health");
  updateModelName();
}

async function loadMeta() {
  state.meta = await fetchJson("/api/meta");
  hydrateModelSettings();
}

async function loadSessions() {
  state.sessions = await fetchJson("/api/sessions");
  renderSessions();
}

async function createSession(title = null) {
  await withBusy("Creating session...", async () => {
    const session = await fetchJson("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    state.sessions.unshift(session);
    renderSessions();
    await selectSession(session.session_id);
    setStatus("Created a fresh session.");
  });
}

async function selectSession(sessionId) {
  state.sessionId = sessionId;
  persistSessionId();
  await withBusy("Loading session...", async () => {
    const data = await fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
    applySessionState(data);
    renderSessions();
    setStatus(data.messages.length ? "Loaded session." : "Ready");
  });
}

async function sendMessage() {
  const message = elements.messageInput.value.trim();
  if (!message || state.busy || !state.sessionId) {
    return;
  }

  const baseMessages = state.messages.slice();
  elements.messageInput.value = "";
  renderStreamingMessages(baseMessages, message, "");

  await withBusy("Thinking...", async () => {
    await streamSse(`/api/sessions/${encodeURIComponent(state.sessionId)}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        settings: currentModelSettings(),
      }),
    }, {
      onChunk(payload) {
        renderStreamingMessages(baseMessages, message, payload.content || "");
      },
      async onDone(payload) {
        applySessionState(payload);
        await loadSessions();
        setStatus("Reply received.");
      },
    });
  }, async (error) => {
    renderMessages(state.messages);
    elements.messageInput.value = message;
    setStatus(error.message, true, "Error");
  });
}

async function streamRegeneration(messageId) {
  const messageIndex = state.messages.findIndex((item) => item.id === messageId);
  if (messageIndex < 0) {
    return;
  }

  const target = state.messages[messageIndex];
  const userIndex = target.role === "assistant"
    ? findPreviousUserIndex(messageIndex)
    : messageIndex;

  const baseMessages = userIndex >= 0 ? state.messages.slice(0, userIndex + 1) : state.messages.slice();

  await withBusy("Regenerating reply...", async () => {
    renderMessages([
      ...baseMessages,
      { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true },
    ]);

    await streamSse(
      `/api/sessions/${encodeURIComponent(state.sessionId)}/messages/${encodeURIComponent(messageId)}/regenerate/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: currentModelSettings() }),
      },
      {
        onChunk(payload) {
          renderMessages([
            ...baseMessages,
            { id: "pending-assistant", role: "assistant", content: payload.content || "", pending: true },
          ]);
        },
        async onDone(payload) {
          applySessionState(payload);
          await loadSessions();
          setStatus("Message regenerated.");
        },
      }
    );
  }, async (error) => {
    renderMessages(state.messages);
    setStatus(error.message, true, "Error");
  });
}

async function mutateMessage(statusLabel, url, options, successMessage) {
  await withBusy(statusLabel, async () => {
    const data = await fetchJson(url, options);
    applySessionState(data);
    await loadSessions();
    setStatus(successMessage);
  });
}

function applySessionState(payload) {
  state.sessionId = payload.session.session_id;
  state.messages = payload.messages || [];
  mergeSession(payload.session);
  persistSessionId();
  syncSystemPromptFromMessages();
  updateSessionMeta();
  renderMessages(state.messages);
}

function mergeSession(session) {
  const index = state.sessions.findIndex((item) => item.session_id === session.session_id);
  if (index >= 0) {
    state.sessions[index] = session;
  } else {
    state.sessions.unshift(session);
  }
  state.sessions.sort((left, right) => right.updated_at.localeCompare(left.updated_at));
}

function renderSessions() {
  if (!state.sessions.length) {
    elements.sessionList.innerHTML = `
      <div class="empty-state compact-empty">
        <p>No sessions yet.</p>
      </div>
    `;
    return;
  }

  elements.sessionList.innerHTML = state.sessions
    .map((session) => {
      const activeClass = session.session_id === state.sessionId ? " session-item-active" : "";
      return `
        <button class="session-item${activeClass}" type="button" data-session-id="${escapeHtml(session.session_id)}">
          <span class="session-title">${escapeHtml(session.title)}</span>
          <span class="session-preview">${escapeHtml(session.preview || "No messages yet")}</span>
        </button>
      `;
    })
    .join("");
}

function renderMessages(messages) {
  if (!messages.length) {
    elements.messages.innerHTML = `
      <div class="empty-state">
        <p>Start a conversation to create the first meaningful session.</p>
      </div>
    `;
    return;
  }

  elements.messages.innerHTML = messages
    .map((message) => {
      const role = escapeHtml(message.role || "assistant");
      const content = escapeHtml(message.content || "");
      const pendingClass = message.pending ? " message-pending" : "";
      const actionButtons =
        role === "system"
          ? `<button class="message-action" type="button" data-action="delete" data-message-id="${escapeHtml(message.id)}">Delete</button>`
          : `
              <button class="message-action" type="button" data-action="edit" data-message-id="${escapeHtml(message.id)}">Edit</button>
              <button class="message-action" type="button" data-action="delete" data-message-id="${escapeHtml(message.id)}">Delete</button>
              <button class="message-action" type="button" data-action="rollback" data-message-id="${escapeHtml(message.id)}">Rollback</button>
              <button class="message-action" type="button" data-action="regenerate" data-message-id="${escapeHtml(message.id)}">Regenerate</button>
            `;
      const tokenUsage = formatTokenUsage(message.token_usage);
      const tokenUsageMarkup = tokenUsage
        ? `<div class="message-usage">${escapeHtml(tokenUsage)}</div>`
        : "";

      return `
        <article class="message message-${role}${pendingClass}">
          <div class="message-topline">
            <span class="message-role">${role}</span>
            <div class="message-actions">
              ${actionButtons}
            </div>
          </div>
          <div>${content}</div>
          ${tokenUsageMarkup}
        </article>
      `;
    })
    .join("");

  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function renderStreamingMessages(baseMessages, userMessage, assistantContent) {
  renderMessages([
    ...baseMessages,
    { id: "pending-user", role: "user", content: userMessage },
    {
      id: "pending-assistant",
      role: "assistant",
      content: assistantContent || "Thinking...",
      pending: true,
    },
  ]);
}

function syncSystemPromptFromMessages() {
  const systemMessage = state.messages.find((message) => message.role === "system");
  elements.systemPrompt.value = systemMessage
    ? systemMessage.content
    : (localStorage.getItem(STORAGE_KEYS.systemPrompt) ?? DEFAULT_SYSTEM_PROMPT);
  localStorage.setItem(STORAGE_KEYS.systemPrompt, elements.systemPrompt.value);
}

function updateSessionMeta() {
  const session = activeSession();
  const usage = session?.token_usage || {};
  elements.sessionId.textContent = state.sessionId || "...";
  elements.activeSessionTitle.textContent = session?.title || "New Session";
  elements.totalTokens.textContent = formatNumber(session?.total_tokens || 0);
  elements.promptTokens.textContent = formatNumber(usage.prompt_tokens || 0);
  elements.contentTokens.textContent = formatNumber(usage.completion_tokens || 0);
  elements.cacheHitTokens.textContent = formatNumber(usage.prompt_cache_hit_tokens || 0);
}

function activeSession() {
  return state.sessions.find((session) => session.session_id === state.sessionId);
}

function persistSessionId() {
  if (state.sessionId) {
    localStorage.setItem(STORAGE_KEYS.sessionId, state.sessionId);
  }
}

function hydrateModelSettings() {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEYS.modelSettings) || "null");
  const defaults = state.meta?.default_chat_settings || {};
  const settings = { ...defaults, ...(saved || {}) };

  elements.providerInput.value = settings.provider || "openai_compatible";
  elements.modelInput.value = settings.model || "";
  elements.baseUrlInput.value = settings.base_url || "";
  elements.apiKeyInput.value = settings.api_key || "";
  elements.temperatureInput.value = String(settings.temperature ?? 1.0);
  updateModelName();
}

function currentModelSettings() {
  const defaults = state.meta?.default_chat_settings || {};
  return {
    provider: elements.providerInput.value.trim() || defaults.provider || "openai_compatible",
    model: elements.modelInput.value.trim() || defaults.model || state.health?.model || null,
    base_url: elements.baseUrlInput.value.trim() || defaults.base_url || null,
    api_key: elements.apiKeyInput.value.trim() || null,
    temperature: Number(elements.temperatureInput.value || "1"),
  };
}

function persistModelSettings() {
  localStorage.setItem(STORAGE_KEYS.modelSettings, JSON.stringify(currentModelSettings()));
}

function updateModelName() {
  const settings = currentModelSettings();
  elements.modelName.textContent = settings.model || state.health?.model || "Not configured";
}

function findPreviousUserIndex(startIndex) {
  for (let index = startIndex - 1; index >= 0; index -= 1) {
    if (state.messages[index]?.role === "user") {
      return index;
    }
  }
  return -1;
}

async function withBusy(label, action, onError) {
  setBusy(true, label);
  try {
    await action();
  } catch (error) {
    if (onError) {
      await onError(error);
    } else {
      setStatus(error.message, true, "Error");
    }
  } finally {
    setBusy(false);
    elements.messageInput.focus();
  }
}

function setBusy(busy, label) {
  state.busy = busy;
  elements.applySystemPromptButton.disabled = busy;
  elements.apiKeyInput.disabled = busy;
  elements.baseUrlInput.disabled = busy;
  elements.sendButton.disabled = busy;
  elements.saveModelSettingsButton.disabled = busy;
  elements.newSessionButton.disabled = busy;
  elements.providerInput.disabled = busy;
  elements.renameSessionButton.disabled = busy;
  elements.deleteSessionButton.disabled = busy;
  elements.messageInput.disabled = busy;
  elements.modelInput.disabled = busy;
  elements.systemPrompt.disabled = busy;
  elements.temperatureInput.disabled = busy;
  if (label) {
    setStatus(label, false, busy ? "Working" : "Ready");
  }
}

function setStatus(message, isError = false, liveLabel = "Ready") {
  elements.statusText.textContent = message;
  elements.statusText.style.color = isError ? "#a03131" : "";
  elements.liveLabel.textContent = liveLabel;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  return data;
}

async function streamSse(url, options, handlers = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed with status ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex !== -1) {
      const rawEvent = buffer.slice(0, boundaryIndex).trim();
      buffer = buffer.slice(boundaryIndex + 2);
      if (rawEvent) {
        await handleSseEvent(rawEvent, handlers);
      }
      boundaryIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }

  const trailing = buffer.trim();
  if (trailing) {
    await handleSseEvent(trailing, handlers);
  }
}

async function handleSseEvent(rawEvent, handlers) {
  let eventName = "message";
  const dataLines = [];

  for (const line of rawEvent.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  const payload = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};

  if (eventName === "chunk" && handlers.onChunk) {
    await handlers.onChunk(payload);
    return;
  }

  if (eventName === "done" && handlers.onDone) {
    await handlers.onDone(payload);
    return;
  }

  if (eventName === "error") {
    throw new Error(payload.detail || "Streaming request failed.");
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTokenUsage(tokenUsage) {
  if (!tokenUsage) {
    return "";
  }

  const parts = [];
  if (typeof tokenUsage.prompt_tokens === "number") {
    parts.push(`prompt ${formatNumber(tokenUsage.prompt_tokens)}`);
  }
  if (typeof tokenUsage.completion_tokens === "number") {
    parts.push(`content ${formatNumber(tokenUsage.completion_tokens)}`);
  }
  if (typeof tokenUsage.prompt_cache_hit_tokens === "number") {
    parts.push(`cache hit ${formatNumber(tokenUsage.prompt_cache_hit_tokens)}`);
  }
  if (typeof tokenUsage.total_tokens === "number") {
    parts.push(`total ${formatNumber(tokenUsage.total_tokens)}`);
  }

  if (parts.length) {
    return parts.join(" | ");
  }

  const numericEntries = Object.entries(tokenUsage).filter(([, value]) => typeof value === "number");
  if (!numericEntries.length) {
    return "";
  }
  return numericEntries.map(([key, value]) => `${key} ${formatNumber(value)}`).join(" | ");
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}
