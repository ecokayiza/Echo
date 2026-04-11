import type {
  DatabaseState,
  HealthResponse,
  MetaResponse,
  ModelSettingsDocument,
  SessionState,
  SessionSummary,
} from "@/types/chat";

async function requestJson<T>(url: string, init?: RequestInit) {
  const response = await fetch(url, init);
  const payload = (await response.json().catch(() => ({}))) as { detail?: string };

  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
  }

  return payload as T;
}

export const api = {
  getHealth() {
    return requestJson<HealthResponse>("/api/health");
  },
  getMeta() {
    return requestJson<MetaResponse>("/api/meta");
  },
  getModelSettings() {
    return requestJson<ModelSettingsDocument>("/api/model-settings");
  },
  updateModelSettings(settings: ModelSettingsDocument) {
    return requestJson<ModelSettingsDocument>("/api/model-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
  },
  listDatabases() {
    return requestJson<DatabaseState>("/api/databases");
  },
  createDatabase(payload?: { name?: string | null; embedding_model_name?: string | null }) {
    return requestJson<DatabaseState>("/api/databases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
  },
  renameDatabase(databaseId: string, name: string) {
    return requestJson<DatabaseState>(`/api/databases/${encodeURIComponent(databaseId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  },
  selectDatabase(databaseId: string) {
    return requestJson<DatabaseState>(`/api/databases/${encodeURIComponent(databaseId)}/select`, {
      method: "POST",
    });
  },
  deleteDatabase(databaseId: string) {
    return requestJson<DatabaseState>(`/api/databases/${encodeURIComponent(databaseId)}`, {
      method: "DELETE",
    });
  },
  listSessions() {
    return requestJson<SessionSummary[]>("/api/sessions");
  },
  createSession(payload?: { title?: string | null; session_id?: string | null }) {
    return requestJson<SessionSummary>("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    });
  },
  getSession(sessionId: string) {
    return requestJson<SessionState>(`/api/sessions/${encodeURIComponent(sessionId)}`);
  },
  renameSession(sessionId: string, title: string) {
    return requestJson<SessionSummary>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
  },
  deleteSession(sessionId: string) {
    return requestJson<{ session_id: string; deleted: boolean }>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
  },
  updateSystemPrompt(sessionId: string, content: string | null) {
    return requestJson<SessionState>(`/api/sessions/${encodeURIComponent(sessionId)}/system-prompt`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  },
  updateMessage(sessionId: string, messageId: string, content: string) {
    return requestJson<SessionState>(
      `/api/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }
    );
  },
  deleteMessage(sessionId: string, messageId: string) {
    return requestJson<SessionState>(
      `/api/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: "DELETE",
      }
    );
  },
  rollbackMessage(sessionId: string, messageId: string) {
    return requestJson<SessionState>(
      `/api/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/rollback`,
      {
        method: "POST",
      }
    );
  },
};
