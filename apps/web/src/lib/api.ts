import type {
  AppSettingsDocument,
  DatabaseDocumentRecord,
  DatabaseState,
  HealthResponse,
  MetaResponse,
  ChatModelConfig,
  EmbeddingModelConfig,
  ModelApiTestResponse,
  ModelSettingsDocument,
  SessionState,
  SessionSummary,
  SkillSettingsDocument,
  UploadJobRecord,
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
  testChatModel(model: ChatModelConfig) {
    return requestJson<ModelApiTestResponse>("/api/model-settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "chat", chat_model: model }),
    });
  },
  testEmbeddingModel(model: EmbeddingModelConfig) {
    return requestJson<ModelApiTestResponse>("/api/model-settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "embedding", embedding_model: model }),
    });
  },
  getAppSettings() {
    return requestJson<AppSettingsDocument>("/api/app-settings");
  },
  updateAppSettings(settings: AppSettingsDocument) {
    return requestJson<AppSettingsDocument>("/api/app-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
  },
  getSkills() {
    return requestJson<SkillSettingsDocument>("/api/skills");
  },
  updateSkills(settings: SkillSettingsDocument) {
    return requestJson<SkillSettingsDocument>("/api/skills", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
  },
  listDatabases() {
    return requestJson<DatabaseState>("/api/databases");
  },
  createDatabase(payload?: { name?: string | null; embedding_model_name?: string | null; backend?: "chroma" | "faiss" | null }) {
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
  uploadDatabaseDocuments(databaseId: string, files: File[], options?: { skipExisting?: boolean }) {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });
    formData.append("skip_existing", String(options?.skipExisting ?? true));
    return requestJson<DatabaseState>(`/api/databases/${encodeURIComponent(databaseId)}/documents`, {
      method: "POST",
      body: formData,
    });
  },
  createDatabaseUploadJob(databaseId: string, files: File[], options?: { skipExisting?: boolean }) {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });
    formData.append("skip_existing", String(options?.skipExisting ?? true));
    return requestJson<UploadJobRecord>(`/api/databases/${encodeURIComponent(databaseId)}/documents/jobs`, {
      method: "POST",
      body: formData,
    });
  },
  getDatabaseUploadJob(databaseId: string, jobId: string) {
    return requestJson<UploadJobRecord>(
      `/api/databases/${encodeURIComponent(databaseId)}/documents/jobs/${encodeURIComponent(jobId)}`
    );
  },
  getCurrentDatabaseUploadJob(databaseId: string) {
    return requestJson<UploadJobRecord | null>(
      `/api/databases/${encodeURIComponent(databaseId)}/documents/jobs/current`
    );
  },
  listDatabaseDocuments(databaseId: string) {
    return requestJson<DatabaseDocumentRecord[]>(`/api/databases/${encodeURIComponent(databaseId)}/documents`);
  },
  renameDatabaseDocument(databaseId: string, documentId: string, sourceName: string) {
    return requestJson<DatabaseDocumentRecord[]>(
      `/api/databases/${encodeURIComponent(databaseId)}/documents/${encodeURIComponent(documentId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_name: sourceName }),
      }
    );
  },
  deleteDatabaseDocument(databaseId: string, documentId: string) {
    return requestJson<DatabaseDocumentRecord[]>(
      `/api/databases/${encodeURIComponent(databaseId)}/documents/${encodeURIComponent(documentId)}`,
      {
        method: "DELETE",
      }
    );
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
