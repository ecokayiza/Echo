const STORAGE_KEYS = {
  sessionId: "echo.session-id",
  systemPrompt: "echo.system-prompt",
} as const;

export const storage = {
  getSessionId() {
    try {
      return window.localStorage.getItem(STORAGE_KEYS.sessionId);
    } catch {
      return null;
    }
  },
  setSessionId(value: string) {
    try {
      window.localStorage.setItem(STORAGE_KEYS.sessionId, value);
    } catch {
      // URL state is still authoritative when storage is unavailable.
    }
  },
  getSystemPrompt() {
    try {
      return window.localStorage.getItem(STORAGE_KEYS.systemPrompt);
    } catch {
      return null;
    }
  },
  setSystemPrompt(value: string) {
    try {
      window.localStorage.setItem(STORAGE_KEYS.systemPrompt, value);
    } catch {
      // Storage can be unavailable on some mobile/private browser modes.
    }
  },
};
