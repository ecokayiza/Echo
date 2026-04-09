type EventPayload = Record<string, unknown>;

interface StreamHandlers {
  onEvent?: (eventName: string, payload: EventPayload) => Promise<void> | void;
  onChunk?: (payload: EventPayload) => Promise<void> | void;
  onDone?: (payload: EventPayload) => Promise<void> | void;
}

async function handleEvent(rawEvent: string, handlers: StreamHandlers) {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of rawEvent.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  const payload = dataLines.length > 0 ? (JSON.parse(dataLines.join("\n")) as EventPayload) : {};

  await handlers.onEvent?.(eventName, payload);

  if (eventName === "chunk") {
    await handlers.onChunk?.(payload);
    return;
  }

  if (eventName === "done") {
    await handlers.onDone?.(payload);
    return;
  }

  if (eventName === "error") {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Streaming request failed.");
  }
}

export async function readEventStream(url: string, init: RequestInit, handlers: StreamHandlers) {
  const response = await fetch(url, init);

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
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

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);

      if (rawEvent) {
        await handleEvent(rawEvent, handlers);
      }

      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }

  const trailing = buffer.trim();
  if (trailing) {
    await handleEvent(trailing, handlers);
  }
}
