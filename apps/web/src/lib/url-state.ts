export function getSessionIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("session");
}

export function setSessionIdInUrl(sessionId: string) {
  const url = new URL(window.location.href);
  url.searchParams.set("session", sessionId);
  window.history.replaceState({}, "", url);
}
