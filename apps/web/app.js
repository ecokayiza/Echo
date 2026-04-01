const STORAGE_KEYS = {
  sessionId: "eco-rag.session-id",
  systemPrompt: "eco-rag.system-prompt",
};

const DEFAULT_SYSTEM_PROMPT =
  "You are the chat assistant for Eco_RAG. Be clear, grounded, and concise. If you are unsure, say so.";

const elements = {
  composer: document.querySelector("#composer"),
  deleteSessionButton: document.querySelector("#deleteSessionButton"),
  liveLabel: document.querySelector("#liveLabel"),
  messageInput: document.querySelector("#messageInput"),
  messages: document.querySelector("#messages"),
  modelName: document.querySelector("#modelName"),
  newSessionButton: document.querySelector("#newSessionButton"),
  renameSessionButton: document.querySelector("#renameSessionButton"),
  sendButton: document.querySelector("#sendButton"),
  sessionId: document.querySelector("#sessionId"),
  sessionList: document.querySelector("#sessionList"),
  statusText: document.querySelector("#statusText"),
  systemPrompt: document.querySelector("#systemPrompt"),
  activeSessionTitle: document.querySelector("#activeSessionTitle"),
};

const state = {
  busy: false,
  messages: [],
  sessions: [],
  sessionId: localStorage.getItem(STORAGE_KEYS.sessionId),
};

elements.systemPrompt.value = localStorage.getItem(STORAGE_KEYS.systemPrompt) || DEFAULT_SYSTEM_PROMPT;

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

elements.systemPrompt.addEventListener("change", async () => {
  localStorage.setItem(STORAGE_KEYS.systemPrompt, elements.systemPrompt.value);
});

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
      "Message updated. Later turns were trimmed."
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
    await withBusy("Regenerating reply...", async () => {
      const data = await fetchJson(
        `/api/sessions/${encodeURIComponent(state.sessionId)}/messages/${encodeURIComponent(messageId)}/regenerate`,
        { method: "POST" }
      );
      applySessionState(data);
      await loadSessions();
      setStatus("Message regenerated.");
    });
  }
});

async function boot() {
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
  const data = await fetchJson("/api/health");
  elements.modelName.textContent = data.model || "Not configured";
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

  const optimisticMessages = [
    ...state.messages,
    { id: "pending-user", role: "user", content: message },
    { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true },
  ];

  elements.messageInput.value = "";
  renderMessages(optimisticMessages);

  await withBusy("Thinking...", async () => {
    const data = await fetchJson(`/api/sessions/${encodeURIComponent(state.sessionId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        system_prompt: elements.systemPrompt.value.trim() || null,
      }),
    });

    applySessionState(data);
    await loadSessions();
    setStatus("Reply received.");
  }, async (error) => {
    renderMessages(state.messages);
    elements.messageInput.value = message;
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
      const regenerateButton =
        role === "system"
          ? ""
          : `<button class="message-action" type="button" data-action="regenerate" data-message-id="${escapeHtml(message.id)}">Regenerate</button>`;

      return `
        <article class="message message-${role}${pendingClass}">
          <div class="message-topline">
            <span class="message-role">${role}</span>
            <div class="message-actions">
              <button class="message-action" type="button" data-action="edit" data-message-id="${escapeHtml(message.id)}">Edit</button>
              <button class="message-action" type="button" data-action="delete" data-message-id="${escapeHtml(message.id)}">Delete</button>
              <button class="message-action" type="button" data-action="rollback" data-message-id="${escapeHtml(message.id)}">Rollback</button>
              ${regenerateButton}
            </div>
          </div>
          <div>${content}</div>
        </article>
      `;
    })
    .join("");

  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function syncSystemPromptFromMessages() {
  const systemMessage = state.messages.find((message) => message.role === "system");
  elements.systemPrompt.value = systemMessage?.content || localStorage.getItem(STORAGE_KEYS.systemPrompt) || DEFAULT_SYSTEM_PROMPT;
  localStorage.setItem(STORAGE_KEYS.systemPrompt, elements.systemPrompt.value);
}

function updateSessionMeta() {
  const session = activeSession();
  elements.sessionId.textContent = state.sessionId || "...";
  elements.activeSessionTitle.textContent = session?.title || "New Session";
}

function activeSession() {
  return state.sessions.find((session) => session.session_id === state.sessionId);
}

function persistSessionId() {
  if (state.sessionId) {
    localStorage.setItem(STORAGE_KEYS.sessionId, state.sessionId);
  }
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
  elements.sendButton.disabled = busy;
  elements.newSessionButton.disabled = busy;
  elements.renameSessionButton.disabled = busy;
  elements.deleteSessionButton.disabled = busy;
  elements.messageInput.disabled = busy;
  elements.systemPrompt.disabled = busy;
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
