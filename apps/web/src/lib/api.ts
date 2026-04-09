import type {
  HealthResponse,
  MetaResponse,
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
