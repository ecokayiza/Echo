import { startTransition, useEffect, useReducer, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatNumber, trimOrNull } from "@/lib/format";
import {
  createEmptyChatModel,
  createEmptyEmbeddingModel,
  getActiveChatModel,
  normalizeModelSettingsDocument,
} from "@/lib/model-settings";
import {
  getDefaultPrompt,
  findPreviousUserIndex,
  getPreferredSessionId,
  getPromptFromMessages,
  mergeSessions,
  sortSessions,
} from "@/lib/session";
import { readEventStream } from "@/lib/sse";
import { storage } from "@/lib/storage";
import { setSessionIdInUrl } from "@/lib/url-state";
import { buildFailedWorkflow, buildPendingWorkflow, normalizeWorkflow } from "@/lib/workflow";
import type {
  ChatModelConfig,
  ChatResponse,
  ConfirmDialogState,
  EmbeddingModelConfig,
  HealthResponse,
  MessageRecord,
  MetaResponse,
  ModelSettingsDocument,
  SessionState,
  SessionSummary,
  WorkflowSnapshot,
} from "@/types/chat";

type StatusTone = "neutral" | "success" | "error";

interface WorkspaceState {
  ready: boolean;
  busy: boolean;
  health: HealthResponse | null;
  meta: MetaResponse | null;
  sessions: SessionSummary[];
  sessionId: string | null;
  messages: MessageRecord[];
  workflow: WorkflowSnapshot | null;
  statusText: string;
  statusTone: StatusTone;
  liveLabel: string;
}

type Action =
  | { type: "bootstrap"; meta: MetaResponse; health: HealthResponse }
  | { type: "ready" }
  | { type: "busy"; busy: boolean; label?: string }
  | { type: "status"; text: string; tone?: StatusTone; liveLabel?: string }
  | { type: "sessions:set"; sessions: SessionSummary[] }
  | { type: "session:select"; sessionId: string | null }
  | { type: "session:summary"; session: SessionSummary }
  | { type: "session:apply"; payload: SessionState; workflow?: WorkflowSnapshot | null }
  | { type: "session:remove"; sessionId: string }
  | { type: "messages:set"; messages: MessageRecord[] }
  | { type: "workflow:set"; workflow: WorkflowSnapshot | null };

const initialState: WorkspaceState = {
  ready: false,
  busy: false,
  health: null,
  meta: null,
  sessions: [],
  sessionId: null,
  messages: [],
  workflow: null,
  statusText: "Connecting...",
  statusTone: "neutral",
  liveLabel: "Booting",
};

function reducer(state: WorkspaceState, action: Action): WorkspaceState {
  switch (action.type) {
    case "bootstrap":
      return {
        ...state,
        health: action.health,
        meta: action.meta,
      };
    case "ready":
      return {
        ...state,
        ready: true,
      };
    case "busy":
      return {
        ...state,
        busy: action.busy,
        statusText: action.label ?? state.statusText,
        liveLabel: action.label ? (action.busy ? "Working" : state.liveLabel) : state.liveLabel,
      };
    case "status":
      return {
        ...state,
        statusText: action.text,
        statusTone: action.tone ?? "neutral",
        liveLabel: action.liveLabel ?? state.liveLabel,
      };
    case "sessions:set":
      return {
        ...state,
        sessions: sortSessions(action.sessions),
      };
    case "session:select":
      return {
        ...state,
        sessionId: action.sessionId,
      };
    case "session:summary":
      return {
        ...state,
        sessions: mergeSessions(state.sessions, action.session),
      };
    case "session:apply":
      return {
        ...state,
        sessionId: action.payload.session.session_id,
        messages: action.payload.messages,
        sessions: mergeSessions(state.sessions, action.payload.session),
        workflow: action.workflow ?? state.workflow,
      };
    case "session:remove":
      return {
        ...state,
        sessions: state.sessions.filter((session) => session.session_id !== action.sessionId),
        sessionId: state.sessionId === action.sessionId ? null : state.sessionId,
        messages: state.sessionId === action.sessionId ? [] : state.messages,
        workflow: state.sessionId === action.sessionId ? null : state.workflow,
      };
    case "messages:set":
      return {
        ...state,
        messages: action.messages,
      };
    case "workflow:set":
      return {
        ...state,
        workflow: action.workflow,
      };
    default:
      return state;
  }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown request error.";
}

function replaceAtIndex<T>(items: T[], index: number, nextItem: T) {
  return items.map((item, itemIndex) => (itemIndex === index ? nextItem : item));
}

export function useChatWorkspace() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [messageDraft, setMessageDraft] = useState("");
  const [systemPromptDraft, setSystemPromptDraft] = useState("");
  const [modelSettings, setModelSettings] = useState<ModelSettingsDocument>(
    normalizeModelSettingsDocument({
      chat_models: [],
      embedding_models: [],
    })
  );
  const [modelSettingsDraft, setModelSettingsDraft] = useState<ModelSettingsDocument>(
    normalizeModelSettingsDocument({
      chat_models: [],
      embedding_models: [],
    })
  );
  const [modelSettingsOpen, setModelSettingsOpen] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null);
  const messageInputRef = useRef<HTMLTextAreaElement | null>(null);

  const activeSession = state.sessions.find((session) => session.session_id === state.sessionId) ?? null;
  const activeChatModel = getActiveChatModel(modelSettings);
  const activeModelName = activeChatModel?.name ?? "Not configured";
  const activePrompt = getPromptFromMessages(state.messages, getDefaultPrompt(state.meta));
  const systemPromptDirty = systemPromptDraft !== activePrompt;
  const totalStoredTokens = state.sessions.reduce((sum, session) => sum + (session.total_tokens || 0), 0);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      try {
        const [health, meta, modelSettings] = await Promise.all([api.getHealth(), api.getMeta(), api.getModelSettings()]);
        if (cancelled) {
          return;
        }

        dispatch({ type: "bootstrap", meta, health });
        const normalizedModelSettings = normalizeModelSettingsDocument(modelSettings);
        setModelSettings(normalizedModelSettings);
        setModelSettingsDraft(normalizedModelSettings);

        const nextPrompt = storage.getSystemPrompt() ?? meta.default_system_prompt;
        setSystemPromptDraft(nextPrompt);
        storage.setSystemPrompt(nextPrompt);

        const sessions = await api.listSessions();
        if (cancelled) {
          return;
        }

        startTransition(() => {
          dispatch({ type: "sessions:set", sessions });
        });

        if (sessions.length === 0) {
          const session = await api.createSession();
          if (cancelled) {
            return;
          }
          storage.setSessionId(session.session_id);
          setSessionIdInUrl(session.session_id);

          const payload = await api.getSession(session.session_id);
          if (cancelled) {
            return;
          }

          startTransition(() => {
            dispatch({ type: "session:apply", payload });
            dispatch({ type: "status", text: "Created a fresh session.", tone: "success", liveLabel: "Ready" });
          });
          setSystemPromptDraft(getPromptFromMessages(payload.messages, meta.default_system_prompt));
          dispatch({ type: "ready" });
          return;
        }

        const preferredSessionId = getPreferredSessionId(sessions);
        if (!preferredSessionId) {
          dispatch({ type: "ready" });
          dispatch({ type: "status", text: "Ready", tone: "success", liveLabel: "Ready" });
          return;
        }

        storage.setSessionId(preferredSessionId);
        setSessionIdInUrl(preferredSessionId);
        dispatch({ type: "session:select", sessionId: preferredSessionId });

        const payload = await api.getSession(preferredSessionId);
        if (cancelled) {
          return;
        }

        startTransition(() => {
          dispatch({ type: "session:apply", payload });
          dispatch({
            type: "status",
            text: payload.messages.length ? "Loaded session." : "Ready",
            tone: "success",
            liveLabel: "Ready",
          });
        });
        setSystemPromptDraft(getPromptFromMessages(payload.messages, meta.default_system_prompt));
        dispatch({ type: "ready" });
      } catch (error) {
        if (cancelled) {
          return;
        }

        dispatch({ type: "ready" });
        dispatch({ type: "status", text: getErrorMessage(error), tone: "error", liveLabel: "Error" });
      }
    }

    void boot();

    return () => {
      cancelled = true;
    };
  }, []);

  function syncSelectedSession(sessionId: string) {
    storage.setSessionId(sessionId);
    setSessionIdInUrl(sessionId);
    dispatch({ type: "session:select", sessionId });
  }

  function applySessionPayload(payload: SessionState, workflow?: WorkflowSnapshot | null) {
    const persistedWorkflow =
      [...payload.messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.workflow)?.workflow ?? null;
    const rawWorkflow = normalizeWorkflow(state.meta, workflow ?? persistedWorkflow);
    // Keep legacy streamed responses compatible if the backend payload did not already persist workflow metadata.
    if (rawWorkflow && payload.messages.length > 0) {
      const lastMessage = payload.messages[payload.messages.length - 1];
      if (lastMessage.role === "assistant" && !lastMessage.workflow) {
        lastMessage.workflow = rawWorkflow;
      }
    }
    
    startTransition(() => {
      dispatch({
        type: "session:apply",
        payload,
        workflow: rawWorkflow,
      });
    });

    syncSelectedSession(payload.session.session_id);

    const nextPrompt = getPromptFromMessages(payload.messages, getDefaultPrompt(state.meta));
    setSystemPromptDraft(nextPrompt);
    storage.setSystemPrompt(nextPrompt);
  }

  async function withBusy(
    label: string,
    action: () => Promise<void>,
    onError?: (message: string) => Promise<void> | void
  ) {
    dispatch({ type: "busy", busy: true, label });

    try {
      await action();
    } catch (error) {
      const detail = getErrorMessage(error);
      if (onError) {
        await onError(detail);
      } else {
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    } finally {
      dispatch({ type: "busy", busy: false });
      window.requestAnimationFrame(() => {
        messageInputRef.current?.focus();
      });
    }
  }

  async function refreshModelSettingsState(nextSettings: ModelSettingsDocument) {
    const [health, meta] = await Promise.all([api.getHealth(), api.getMeta()]);
    const normalizedModelSettings = normalizeModelSettingsDocument(nextSettings);
    setModelSettings(normalizedModelSettings);
    setModelSettingsDraft(normalizedModelSettings);
    dispatch({ type: "bootstrap", meta, health });
  }

  async function persistModelSettings(nextSettings: ModelSettingsDocument) {
    const savedSettings = await api.updateModelSettings(normalizeModelSettingsDocument(nextSettings));
    await refreshModelSettingsState(savedSettings);
    return savedSettings;
  }

  async function loadSessionSnapshot(sessionId: string) {
    const payload = await api.getSession(sessionId);
    applySessionPayload(payload);
    return payload;
  }

  async function selectSession(sessionId: string) {
    syncSelectedSession(sessionId);

    await withBusy("Loading session...", async () => {
      const payload = await loadSessionSnapshot(sessionId);
      dispatch({
        type: "status",
        text: payload.messages.length ? "Loaded session." : "Ready",
        tone: "success",
        liveLabel: "Ready",
      });
    });
  }

  async function createSession(title?: string | null) {
    await withBusy("Creating session...", async () => {
      const session = await api.createSession({ title: title ?? null });
      syncSelectedSession(session.session_id);
      await loadSessionSnapshot(session.session_id);
      dispatch({ type: "status", text: "Created a fresh session.", tone: "success", liveLabel: "Ready" });
    });
  }

  async function applySystemPrompt() {
    if (!state.sessionId) {
      return;
    }

    await withBusy(
      "Updating system prompt...",
      async () => {
        const payload = await api.updateSystemPrompt(state.sessionId!, trimOrNull(systemPromptDraft));
        applySessionPayload(payload);
        storage.setSystemPrompt(systemPromptDraft);
        dispatch({ type: "status", text: "System prompt updated.", tone: "success", liveLabel: "Ready" });
      },
      async (detail) => {
        setSystemPromptDraft(activePrompt);
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    );
  }

  function resetSystemPromptDraft() {
    setSystemPromptDraft(activePrompt || state.meta?.default_system_prompt || "");
  }

  function setActiveChatModel(name: string) {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        active_chat_model: name,
      })
    );
  }

  function setActiveEmbeddingModel(name: string) {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        active_embedding_model: name,
      })
    );
  }

  function updateChatModel<Key extends keyof ChatModelConfig>(index: number, key: Key, value: ChatModelConfig[Key]) {
    setModelSettingsDraft((current) => {
      const previous = current.chat_models[index];
      if (!previous) {
        return current;
      }

      const nextName = key === "name" ? (typeof value === "string" ? value : previous.name) : previous.name;
      const nextActiveName =
        key === "name" && current.active_chat_model === previous.name && typeof value === "string"
          ? value
          : current.active_chat_model;

      return normalizeModelSettingsDocument({
        ...current,
        active_chat_model: nextActiveName,
        chat_models: replaceAtIndex(current.chat_models, index, {
          ...previous,
          [key]: value,
          ...(key === "name" ? { name: nextName } : {}),
        }),
      });
    });
  }

  function updateEmbeddingModel<Key extends keyof EmbeddingModelConfig>(
    index: number,
    key: Key,
    value: EmbeddingModelConfig[Key]
  ) {
    setModelSettingsDraft((current) => {
      const previous = current.embedding_models[index];
      if (!previous) {
        return current;
      }

      const nextName = key === "name" ? (typeof value === "string" ? value : previous.name) : previous.name;
      const nextActiveName =
        key === "name" && current.active_embedding_model === previous.name && typeof value === "string"
          ? value
          : current.active_embedding_model;

      return normalizeModelSettingsDocument({
        ...current,
        active_embedding_model: nextActiveName,
        embedding_models: replaceAtIndex(current.embedding_models, index, {
          ...previous,
          [key]: value,
          ...(key === "name" ? { name: nextName } : {}),
        }),
      });
    });
  }

  function addChatModel() {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        chat_models: [...current.chat_models, createEmptyChatModel(current.chat_models.length + 1)],
      })
    );
  }

  function addEmbeddingModel() {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        embedding_models: [...current.embedding_models, createEmptyEmbeddingModel(current.embedding_models.length + 1)],
      })
    );
  }

  function removeChatModel(index: number) {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        chat_models: current.chat_models.filter((_, itemIndex) => itemIndex !== index),
      })
    );
  }

  function removeEmbeddingModel(index: number) {
    setModelSettingsDraft((current) =>
      normalizeModelSettingsDocument({
        ...current,
        embedding_models: current.embedding_models.filter((_, itemIndex) => itemIndex !== index),
      })
    );
  }

  function openModelSettings() {
    setModelSettingsDraft(modelSettings);
    setModelSettingsOpen(true);
  }

  function closeModelSettings() {
    setModelSettingsDraft(modelSettings);
    setModelSettingsOpen(false);
  }

  async function selectActiveChatModel(name: string) {
    if (!name || modelSettings.active_chat_model === name) {
      return;
    }

    await withBusy(
      "Switching active model...",
      async () => {
        const nextSettings = normalizeModelSettingsDocument({
          ...modelSettings,
          active_chat_model: name,
        });
        await persistModelSettings(nextSettings);
        dispatch({ type: "status", text: "Active model updated.", tone: "success", liveLabel: "Ready" });
      },
      async (detail) => {
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    );
  }

  async function saveModelSettings() {
    await withBusy(
      "Saving model settings...",
      async () => {
        await persistModelSettings(modelSettingsDraft);
        setModelSettingsOpen(false);
        dispatch({ type: "status", text: "Model settings saved.", tone: "success", liveLabel: "Ready" });
      },
      async (detail) => {
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    );
  }

  async function renameSession(targetSession: SessionSummary, nextTitle: string) {
    if (state.busy) {
      return;
    }

    const cleanedTitle = nextTitle.trim();
    if (!cleanedTitle) {
      dispatch({ type: "status", text: "Session title cannot be empty.", tone: "error", liveLabel: "Error" });
      return;
    }

    await withBusy("Renaming session...", async () => {
      const session = await api.renameSession(targetSession.session_id, cleanedTitle);
      startTransition(() => {
        dispatch({ type: "session:summary", session });
      });
      dispatch({ type: "status", text: "Session renamed.", tone: "success", liveLabel: "Ready" });
    });
  }

  function openDeleteSessionDialog(targetSession?: SessionSummary) {
    const target = targetSession ?? activeSession;
    if (!target || state.busy) {
      return;
    }

    setConfirmDialog({
      title: "Delete Session",
      description: `Delete "${target.title}" and remove its persisted chat history?`,
      confirmLabel: "Delete Session",
      tone: "danger",
      onConfirm: async () => {
        await withBusy("Deleting session...", async () => {
          const deletedId = target.session_id;
          const remainingSessions = state.sessions.filter((session) => session.session_id !== deletedId);

          await api.deleteSession(deletedId);
          startTransition(() => {
            dispatch({ type: "session:remove", sessionId: deletedId });
          });

          setConfirmDialog(null);

          if (deletedId === state.sessionId && remainingSessions.length > 0) {
            const nextSessionId = remainingSessions[0].session_id;
            syncSelectedSession(nextSessionId);
            await loadSessionSnapshot(nextSessionId);
          } else if (deletedId === state.sessionId) {
            const session = await api.createSession();
            syncSelectedSession(session.session_id);
            await loadSessionSnapshot(session.session_id);
          }

          dispatch({ type: "status", text: "Session deleted.", tone: "success", liveLabel: "Ready" });
        });
      },
    });
  }

  async function updateMessageContent(message: MessageRecord, nextContent: string) {
    if (!state.sessionId || state.busy) {
      return;
    }

    const content = nextContent.trim();
    if (!content) {
      dispatch({ type: "status", text: "Message content cannot be empty.", tone: "error", liveLabel: "Error" });
      return;
    }

    await withBusy("Updating message...", async () => {
      const payload = await api.updateMessage(state.sessionId!, message.id, content);
      applySessionPayload(payload);
      dispatch({ type: "status", text: "Message updated.", tone: "success", liveLabel: "Ready" });
    });
  }

  function openDeleteMessageDialog(message: MessageRecord) {
    if (!state.sessionId || state.busy) {
      return;
    }

    setConfirmDialog({
      title: "Delete Message",
      description:
        message.role === "system"
          ? "Clear the system prompt while keeping the conversation?"
          : "Delete only this message and keep the rest of the conversation?",
      confirmLabel: "Delete Message",
      tone: "danger",
      onConfirm: async () => {
        await withBusy("Deleting message...", async () => {
          const payload = await api.deleteMessage(state.sessionId!, message.id);
          applySessionPayload(payload);
          setConfirmDialog(null);
          dispatch({
            type: "status",
            text: message.role === "system" ? "System prompt cleared." : "Message deleted.",
            tone: "success",
            liveLabel: "Ready",
          });
        });
      },
    });
  }

  function openRollbackDialog(message: MessageRecord) {
    if (!state.sessionId || state.busy) {
      return;
    }

    setConfirmDialog({
      title: "Rollback Session",
      description: "Keep this message and remove everything that comes after it?",
      confirmLabel: "Rollback",
      onConfirm: async () => {
        await withBusy("Rolling back session...", async () => {
          const payload = await api.rollbackMessage(state.sessionId!, message.id);
          applySessionPayload(payload);
          setConfirmDialog(null);
          dispatch({ type: "status", text: "Rolled back to the selected message.", tone: "success", liveLabel: "Ready" });
        });
      },
    });
  }

  async function sendMessage() {
    const outgoing = messageDraft.trim();
    if (!outgoing || !state.sessionId || state.busy) {
      return;
    }

    const stableMessages = [...state.messages];
    const pendingWorkflow = buildPendingWorkflow(state.meta, outgoing);
    let currentWorkflow = pendingWorkflow;

    setMessageDraft("");
    startTransition(() => {
      dispatch({ type: "workflow:set", workflow: pendingWorkflow });
      dispatch({
        type: "messages:set",
        messages: [
          ...stableMessages,
          { id: "pending-user", role: "user", content: outgoing, pending: true },
          { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true, workflow: currentWorkflow },
        ],
      });
    });

    await withBusy(
      "Thinking...",
      async () => {
        await readEventStream(
          `/api/sessions/${encodeURIComponent(state.sessionId!)}/messages/stream`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: outgoing,
            }),
          },
          {
            onEvent: async (eventName, payload) => {
              if (eventName !== "workflow") {
                return;
              }

              const workflow = normalizeWorkflow(state.meta, payload as unknown as WorkflowSnapshot);
              if (!workflow) {
                throw new Error("Workflow event payload is empty.");
              }
              currentWorkflow = workflow;
              startTransition(() => {
                dispatch({ type: "workflow:set", workflow });
                dispatch({
                  type: "messages:set",
                  messages: [
                    ...stableMessages,
                    { id: "pending-user", role: "user", content: outgoing, pending: true },
                    { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true, workflow: currentWorkflow },
                  ],
                });
              });
              dispatch({
                type: "status",
                text: workflow.active_node ? `Workflow ${workflow.status} at ${workflow.active_node}.` : `Workflow ${workflow.status}.`,
                liveLabel: "Working",
              });
            },
            onChunk: async (payload) => {
              if (typeof payload.content !== "string") {
                throw new Error("Streaming chunk is missing content.");
              }
              const content = payload.content;
              startTransition(() => {
                dispatch({
                  type: "messages:set",
                  messages: [
                    ...stableMessages,
                    { id: "pending-user", role: "user", content: outgoing, pending: true },
                    { id: "pending-assistant", role: "assistant", content, pending: true, workflow: currentWorkflow },
                  ],
                });
              });
            },
            onDone: async (payload) => {
              const response = payload as unknown as ChatResponse;
              applySessionPayload(response, response.workflow);
              dispatch({ type: "status", text: "Reply received.", tone: "success", liveLabel: "Ready" });
            },
          }
        );
      },
      async (detail) => {
        setMessageDraft(outgoing);
        startTransition(() => {
          dispatch({ type: "messages:set", messages: stableMessages });
          dispatch({
            type: "workflow:set",
            workflow: buildFailedWorkflow(pendingWorkflow, detail),
          });
        });
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    );
  }

  async function regenerateMessage(message: MessageRecord) {
    if (!state.sessionId || state.busy) {
      return;
    }

    const messageIndex = state.messages.findIndex((item) => item.id === message.id);
    if (messageIndex < 0) {
      return;
    }

    const userIndex =
      message.role === "assistant" ? findPreviousUserIndex(state.messages, messageIndex) : messageIndex;
    const baseMessages = userIndex >= 0 ? state.messages.slice(0, userIndex + 1) : [...state.messages];
    const question = baseMessages.at(-1)?.content;
    if (!question) {
      throw new Error("Cannot regenerate without a user question.");
    }
    const pendingWorkflow = buildPendingWorkflow(state.meta, question);
    let currentWorkflow = pendingWorkflow;

    startTransition(() => {
      dispatch({ type: "workflow:set", workflow: pendingWorkflow });
      dispatch({
        type: "messages:set",
        messages: [...baseMessages, { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true, workflow: currentWorkflow }],
      });
    });

    await withBusy(
      "Regenerating reply...",
      async () => {
        await readEventStream(
          `/api/sessions/${encodeURIComponent(state.sessionId!)}/messages/${encodeURIComponent(message.id)}/regenerate/stream`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          },
          {
            onEvent: async (eventName, payload) => {
              if (eventName !== "workflow") {
                return;
              }

              const workflow = normalizeWorkflow(state.meta, payload as unknown as WorkflowSnapshot);
              if (!workflow) {
                throw new Error("Workflow event payload is empty.");
              }
              currentWorkflow = workflow;
              startTransition(() => {
                dispatch({ type: "workflow:set", workflow });
                dispatch({
                  type: "messages:set",
                  messages: [...baseMessages, { id: "pending-assistant", role: "assistant", content: "Thinking...", pending: true, workflow: currentWorkflow }],
                });
              });
              dispatch({
                type: "status",
                text: workflow.active_node ? `Workflow ${workflow.status} at ${workflow.active_node}.` : `Workflow ${workflow.status}.`,
                liveLabel: "Working",
              });
            },
            onChunk: async (payload) => {
              if (typeof payload.content !== "string") {
                throw new Error("Streaming chunk is missing content.");
              }
              const content = payload.content;
              startTransition(() => {
                dispatch({
                  type: "messages:set",
                  messages: [...baseMessages, { id: "pending-assistant", role: "assistant", content, pending: true, workflow: currentWorkflow }],
                });
              });
            },
            onDone: async (payload) => {
              const response = payload as unknown as ChatResponse;
              applySessionPayload(response, response.workflow);
              dispatch({ type: "status", text: "Message regenerated.", tone: "success", liveLabel: "Ready" });
            },
          }
        );
      },
      async (detail) => {
        startTransition(() => {
          dispatch({ type: "messages:set", messages: state.messages });
          dispatch({
            type: "workflow:set",
            workflow: buildFailedWorkflow(pendingWorkflow, detail),
          });
        });
        dispatch({ type: "status", text: detail, tone: "error", liveLabel: "Error" });
      }
    );
  }

  return {
    workspace: {
      state,
      activeSession,
      activeModelName,
      modelNames: modelSettings.chat_models.map((item) => item.name),
      totalStoredTokens,
      formatNumber,
    },
    drafts: {
      messageDraft,
      setMessageDraft,
      systemPromptDraft,
      setSystemPromptDraft,
      systemPromptDirty,
      modelSettingsDraft,
      modelSettingsOpen,
      setActiveChatModel,
      setActiveEmbeddingModel,
      updateChatModel,
      updateEmbeddingModel,
      addChatModel,
      addEmbeddingModel,
      removeChatModel,
      removeEmbeddingModel,
    },
    dialogs: {
      confirmDialog,
      setConfirmDialog,
    },
    refs: {
      messageInputRef,
    },
    actions: {
      selectSession,
      createSession,
      applySystemPrompt,
      resetSystemPromptDraft,
      openModelSettings,
      closeModelSettings,
      selectActiveChatModel,
      saveModelSettings,
      renameSession,
      openDeleteSessionDialog,
      updateMessageContent,
      openDeleteMessageDialog,
      openRollbackDialog,
      regenerateMessage,
      sendMessage,
    },
  };
}
