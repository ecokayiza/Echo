# API App

This directory hosts the FastAPI backend for the Eco_RAG chat app.

## Run

```bash
python -m uvicorn apps.api.app.main:app --reload
```

If Windows reports `Failed to canonicalize script path`, use:

```bash
python run_api.py
```

After startup:

- UI: `http://127.0.0.1:8000/ui/`
- OpenAPI docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Overview

The API is session-first.

- A chat session has metadata like `session_id`, `title`, timestamps, message count, preview text, aggregated `token_usage`, and `total_tokens`.
- Messages are stored per session and persisted on disk under `memory/chat_sessions/`.
- Session and message usage use the same four counters: `prompt_tokens`, `prompt_cache_hit_tokens`, `completion_tokens`, and `total_tokens`.
- The current code targets this format directly instead of carrying backward-compat branches for older layouts.
- Message operations are handled inside the chat layer through unified in-chat actions: `send`, `edit`, `delete`, `rollback`, `regenerate`, and `system_prompt`.
- The web UI uses streaming endpoints by default for send and regenerate.
- Requests can optionally include per-user chat model settings such as `model`, `base_url`, `api_key`, and `temperature`.

## Response Shapes

These names describe API views, not three different records stored on disk.

- `Session summary` is the compact metadata object used in `GET /api/sessions`.
- `Session state` is `session summary + full messages`.
- `Chat response` is `session state + convenience fields for the newest model turn`.

The top-level `reply` and `token_usage` in a chat response are intentional. They only describe the newest assistant generation, and they are there so the frontend can use the final reply directly without diffing the full message list.

### Session summary

```json
{
  "session_id": "session-123",
  "title": "Weather chat",
  "created_at": "2026-04-02T09:00:00+00:00",
  "updated_at": "2026-04-02T09:05:00+00:00",
  "message_count": 3,
  "preview": "It will be warm today.",
  "token_usage": {
    "prompt_tokens": 123,
    "completion_tokens": 27,
    "total_tokens": 150,
    "prompt_cache_hit_tokens": 64
  },
  "total_tokens": 150
}
```

### Session state

```json
{
  "session": {
    "session_id": "session-123",
    "title": "Weather chat",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 3,
    "preview": "It will be warm today.",
    "token_usage": {
      "prompt_tokens": 123,
      "completion_tokens": 27,
      "total_tokens": 150,
      "prompt_cache_hit_tokens": 64
    },
    "total_tokens": 150
  },
  "messages": [
    {
      "id": "message-1",
      "role": "system",
      "content": "Be clear and concise."
    },
    {
      "id": "message-2",
      "role": "user",
      "content": "How is the weather?"
    },
    {
      "id": "message-3",
      "role": "assistant",
      "content": "It will be warm today.",
      "token_usage": {
        "prompt_tokens": 123,
        "prompt_cache_hit_tokens": 64,
        "completion_tokens": 27,
        "total_tokens": 150
      }
    }
  ]
}
```

Notes:

- `session.token_usage` is the session-level aggregate.
- `messages[*].token_usage` is per-message usage.
- Session and message usage expose the same four counters.

### Chat response

```json
{
  "session": {
    "session_id": "session-123",
    "title": "Weather chat",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 3,
    "preview": "It will be warm today.",
    "token_usage": {
      "prompt_tokens": 123,
      "completion_tokens": 27,
      "total_tokens": 150,
      "prompt_cache_hit_tokens": 64
    },
    "total_tokens": 150
  },
  "messages": [
    {
      "id": "message-1",
      "role": "system",
      "content": "Be clear and concise."
    },
    {
      "id": "message-2",
      "role": "user",
      "content": "How is the weather?"
    },
    {
      "id": "message-3",
      "role": "assistant",
      "content": "It will be warm today.",
      "token_usage": {
        "prompt_tokens": 123,
        "completion_tokens": 27,
        "total_tokens": 150,
        "prompt_cache_hit_tokens": 64
      }
    }
  ],
  "reply": "It will be warm today.",
  "token_usage": {
    "prompt_tokens": 123,
    "completion_tokens": 27,
    "total_tokens": 150,
    "prompt_cache_hit_tokens": 64
  }
}
```

Notes:

- `reply` is the newest assistant text only.
- Top-level `token_usage` is the newest assistant generation only.
- The same newest assistant turn also appears in `messages`.
- This duplication is intentional because it makes streaming and final UI updates simpler.

## Endpoints

### `GET /`

Redirects to the lightweight frontend at `/ui/`.

### `GET /api/health`

Returns backend health and current configured model.

Example response:

```json
{
  "status": "ok",
  "model": "deepseek-chat"
}
```

### `GET /api/meta`

Returns frontend metadata for workflow enums and the default system prompt.

Example response:

```json
{
  "workflow_statuses": ["queued", "running", "completed", "failed"],
  "workflow_steps": ["query_processing", "retrieval", "generation", "finalization"],
  "default_system_prompt": "You are the chat assistant for Eco_RAG. Be clear, grounded, and concise. If you are unsure, say so.",
  "default_chat_settings": {
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "api_key": null,
    "base_url": "https://api.deepseek.com",
    "temperature": 1.0
  }
}
```

### `GET /api/sessions`

Lists chat sessions ordered by most recently updated.

Response:

- `200 OK`
- Body: `Session summary[]`

### `POST /api/sessions`

Creates a new session.

Request body:

```json
{
  "session_id": "optional-custom-id",
  "title": "Optional title"
}
```

Notes:

- If `session_id` is omitted, the backend generates a UUID.
- If `title` is omitted, the title starts as `New Session`.

Response:

- `200 OK`
- Body: `Session summary`

### `GET /api/sessions/{session_id}`

Returns session metadata plus the full message history.

Response:

- `200 OK`
- Body: `Session state`

### `PATCH /api/sessions/{session_id}`

Renames a session.

Request body:

```json
{
  "title": "Renamed session"
}
```

Response:

- `200 OK`
- Body: `Session summary`

Error:

- `400 Bad Request` if `title` is empty

### `PATCH /api/sessions/{session_id}/system-prompt`

Creates, updates, or clears the session system prompt without removing later messages.

Request body:

```json
{
  "content": "Be practical and direct."
}
```

To clear the prompt:

```json
{
  "content": null
}
```

Response:

- `200 OK`
- Body: `Session state`

### `DELETE /api/sessions/{session_id}`

Deletes a session and its persisted history.

Response:

```json
{
  "session_id": "session-123",
  "deleted": true
}
```

### `POST /api/sessions/{session_id}/messages`

Sends a new user message and generates an assistant reply.

Request body:

```json
{
  "message": "Explain retrieval-augmented generation simply.",
  "system_prompt": "Be concise and practical.",
  "settings": {
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "api_key": null,
    "base_url": "https://api.deepseek.com",
    "temperature": 0.7
  }
}
```

Notes:

- `system_prompt` is optional.
- When provided, it is treated as an in-chat system message operation before the send.
- `settings` is optional and overrides the default model configuration for that request.
- If the session title is still auto-managed, the first user message becomes the title.

Response:

- `200 OK`
- Body: `Chat response`

Errors:

- `400 Bad Request` for invalid input like an empty message
- `500 Internal Server Error` for model/provider failures

### `POST /api/sessions/{session_id}/messages/stream`

Streams the assistant reply as `text/event-stream`.

Request body:

- Same as `POST /api/sessions/{session_id}/messages`

Events:

- `chunk`: incremental assistant text
- `done`: final `Chat response`
- `error`: failure payload with `detail`

### `PATCH /api/sessions/{session_id}/messages/{message_id}`

Edits a message in place.

Request body:

```json
{
  "content": "Edited message content"
}
```

Notes:

- Editing a message does not remove later messages.
- System prompt changes should go through `PATCH /api/sessions/{session_id}/system-prompt`.

Response:

- `200 OK`
- Body: `Session state`

### `DELETE /api/sessions/{session_id}/messages/{message_id}`

Deletes a message and all following messages.

Notes:

- Deleting the system message clears the system prompt and keeps the remaining conversation.
- Deleting a middle user or assistant message truncates the thread at that point.

Response:

- `200 OK`
- Body: `Session state`

### `POST /api/sessions/{session_id}/messages/{message_id}/rollback`

Rolls the session back to a specific message.

Notes:

- The target message is kept.
- Everything after it is removed.

Response:

- `200 OK`
- Body: `Session state`

### `POST /api/sessions/{session_id}/messages/{message_id}/regenerate`

Regenerates the assistant reply for a message branch.

Notes:

- If the target is an assistant message, the backend finds the preceding user message and regenerates from there.
- If the target is a user message, the backend regenerates the assistant reply directly from that point.
- System messages cannot be regenerated.

Response:

- `200 OK`
- Body: `Chat response`

### `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

Streams the regenerated assistant reply as `text/event-stream`.

Request body:

```json
{
  "settings": {
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "api_key": null,
    "base_url": "https://api.deepseek.com",
    "temperature": 0.7
  }
}
```

Events:

- `chunk`: incremental assistant text
- `done`: final `Chat response`
- `error`: failure payload with `detail`

## Message Roles

Current message roles used by the API:

- `system`
- `user`
- `assistant`

## Error Format

Validation and request errors are returned as standard FastAPI error payloads.

Example:

```json
{
  "detail": "Message cannot be empty."
}
```

For chat/model failures, the API wraps the backend exception:

```json
{
  "detail": "Chat request failed: Missing API key. Set API_KEY or OPENAI_API_KEY in your environment or .env file."
}
```
