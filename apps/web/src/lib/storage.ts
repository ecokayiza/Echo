const STORAGE_KEYS = {
  sessionId: "echo.session-id",
  systemPrompt: "echo.system-prompt",
} as const;

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
};
