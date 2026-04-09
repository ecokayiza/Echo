import type { ChatSettings } from "@/types/chat";

const STORAGE_KEYS = {
  sessionId: "eco-rag.session-id",
  systemPrompt: "eco-rag.system-prompt",
  modelSettings: "eco-rag.model-settings",
} as const;

function parseJson<T>(value: string | null): T | null {
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export const storage = {
  getSessionId() {
    return window.localStorage.getItem(STORAGE_KEYS.sessionId);
  },
  setSessionId(value: string) {
    window.localStorage.setItem(STORAGE_KEYS.sessionId, value);
  },
  getSystemPrompt() {
    return window.localStorage.getItem(STORAGE_KEYS.systemPrompt);
  },
  setSystemPrompt(value: string) {
    window.localStorage.setItem(STORAGE_KEYS.systemPrompt, value);
  },
  getModelSettings() {
    return parseJson<Partial<ChatSettings>>(window.localStorage.getItem(STORAGE_KEYS.modelSettings));
  },
  setModelSettings(value: ChatSettings) {
    window.localStorage.setItem(STORAGE_KEYS.modelSettings, JSON.stringify(value));
  },
};
