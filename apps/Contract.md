# 前后端接口契约

这份文档定义 `apps/web` 与 `apps/api` 当前使用的真实协议。

## 全局规则

- 普通 HTTP 请求和响应都使用 JSON
- 所有时间使用 UTC ISO-8601 字符串
- SSE 事件使用 `event: <name>` + `data: <json>`
- message `role` 允许：
  - `system`
  - `user`
  - `assistant`
  - `tool`
- workflow steps 固定为：
  - `plan`
  - `retrieve`
  - `tool`
  - `think`
  - `answer`
- workflow statuses 固定为：
  - `queued`
  - `running`
  - `completed`
  - `failed`

## 共享结构

### `TokenUsage`

```json
{
  "prompt_tokens": 120,
  "prompt_cache_hit_tokens": 64,
  "completion_tokens": 30,
  "total_tokens": 150
}
```

### `SessionSummary`

```json
{
  "session_id": "session-123",
  "title": "Repo workflow",
  "created_at": "2026-04-02T09:00:00+00:00",
  "updated_at": "2026-04-02T09:05:00+00:00",
  "message_count": 5,
  "preview": "answer text",
  "token_usage": {
    "prompt_tokens": 123,
    "completion_tokens": 27,
    "total_tokens": 150
  },
  "total_tokens": 150
}
```

### `MessageRecord`

```json
{
  "id": "message-3",
  "role": "assistant",
  "content": "<plan>\nNeed retrieval.\n</plan>",
  "message_type": "plan",
  "workflow_turn_id": "user-1",
  "tool_name": null,
  "token_usage": {
    "prompt_tokens": 5,
    "completion_tokens": 1,
    "total_tokens": 6
  }
}
```

新 workflow 内部消息使用 paired XML-style tags。

可选字段：

- `message_type`
- `workflow_turn_id`
- `tool_name`
- `token_usage`

`message_type` 允许：

- `system`
- `user`
- `plan`
- `think`
- `tool`
- `answer`

只读消息：

- `plan`
- `think`
- `tool`

这些消息不允许：

- edit
- delete
- rollback
- regenerate

### `SessionState`

```json
{
  "session": {
    "session_id": "session-123",
    "title": "Repo workflow",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 5,
    "preview": "answer text",
    "token_usage": {
      "prompt_tokens": 123,
      "completion_tokens": 27,
      "total_tokens": 150
    },
    "total_tokens": 150
  },
  "messages": []
}
```

### `DatabaseRecord`

```json
{
  "id": "db-123",
  "name": "Local Docs",
  "collection_name": "db_local_docs_ab12cd34",
  "embedding_model_name": "Local Qwen3 Embedding",
  "document_count": 42,
  "created_at": "2026-04-11T11:00:00+00:00",
  "updated_at": "2026-04-11T11:05:00+00:00"
}
```

### `DatabaseState`

```json
{
  "active_database_id": "db-123",
  "databases": []
}
```

### `WorkflowNodeStatus`

```json
{
  "node": "plan",
  "status": "completed",
  "detail": "Will retrieve more context."
}
```

### `WorkflowLog`

```json
{
  "level": "error",
  "node": "tool",
  "message": "Database is not configured."
}
```

### `WorkflowSnapshot`

```json
{
  "workflow_turn_id": "user-1",
  "query": "Explain the repo workflow",
  "answer": "Here is the answer.",
  "status": "completed",
  "active_node": null,
  "node_statuses": [
    { "node": "plan", "status": "completed", "detail": "Will retrieve more context." },
    { "node": "retrieve", "status": "completed", "detail": null },
    { "node": "tool", "status": "completed", "detail": "web_search" },
    { "node": "think", "status": "completed", "detail": "Answer is ready." },
    { "node": "answer", "status": "completed", "detail": null }
  ],
  "logs": [],
  "errors": []
}
```

约束：

- `node_statuses` 必须存在
- `node_statuses.length` 必须等于 `meta.workflow_steps.length`
- `active_node` 必须存在，结束时可为 `null`
- `logs` 必须存在
- `errors` 必须存在

### `ChatResponse`

```json
{
  "session": {
    "session_id": "session-123",
    "title": "Repo workflow",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 5,
    "preview": "Here is the answer.",
    "token_usage": {
      "prompt_tokens": 123,
      "completion_tokens": 27,
      "total_tokens": 150
    },
    "total_tokens": 150
  },
  "messages": [],
  "reply": "Here is the answer.",
  "token_usage": {
    "prompt_tokens": 123,
    "completion_tokens": 27,
    "total_tokens": 150
  },
  "workflow": {
    "workflow_turn_id": "user-1",
    "query": "Explain the repo workflow",
    "answer": "Here is the answer.",
    "status": "completed",
    "active_node": null,
    "node_statuses": [],
    "logs": [],
    "errors": []
  }
}
```

约束：

- `session` 和 `messages` 必须是最终已持久化状态
- 顶层 `reply` 是本次新生成的 final answer
- 顶层 `token_usage` 是这次 workflow 内部记录的聚合 usage
- 顶层 `workflow` 是本轮 live workflow 的最终 snapshot
- `messages[*]` 不再持久化 `workflow` 字段

Embedding provider 本身不属于 `apps/web <-> apps/api` 契约。

约定只有一条：

- `models.json` 里的 embedding `base_url` 必须指向一个外部 OpenAI 兼容 `/v1/embeddings` 服务

## HTTP 接口

### `GET /api/health`

响应示例：

```json
{
  "status": "ok",
  "model": "deepseek-chat"
}
```

### `GET /api/meta`

响应示例：

```json
{
  "workflow_statuses": ["queued", "running", "completed", "failed"],
  "workflow_steps": ["plan", "retrieve", "tool", "think", "answer"],
  "default_system_prompt": "..."
}
```

### `GET /api/model-settings`

读取根目录 `models.json`。

### `PUT /api/model-settings`

完整覆盖保存根目录 `models.json`。

### `GET /api/databases`

响应：

- `DatabaseState`

### `POST /api/databases`

请求：

```json
{
  "name": "Local Docs",
  "embedding_model_name": "Local Qwen3 Embedding"
}
```

响应：

- `DatabaseState`

### `PATCH /api/databases/{database_id}`

请求：

```json
{
  "name": "Renamed Database"
}
```

响应：

- `DatabaseState`

### `POST /api/databases/{database_id}/select`

响应：

- `DatabaseState`

### `DELETE /api/databases/{database_id}`

响应：

- `DatabaseState`

### `GET /api/sessions`

响应：

- `SessionSummary[]`

### `POST /api/sessions`

请求：

```json
{
  "title": "Optional title",
  "session_id": "optional-session-id"
}
```

响应：

- `SessionSummary`

### `GET /api/sessions/{session_id}`

响应：

- `SessionState`

### `PATCH /api/sessions/{session_id}`

请求：

```json
{
  "title": "New title"
}
```

响应：

- `SessionSummary`

### `DELETE /api/sessions/{session_id}`

响应：

```json
{
  "session_id": "session-123",
  "deleted": true
}
```

### `PATCH /api/sessions/{session_id}/system-prompt`

请求：

```json
{
  "content": "Be concise."
}
```

清空会被拒绝，因为 session 必须始终保留一个 system prompt。

响应：

- `SessionState`

### `PATCH /api/sessions/{session_id}/messages/{message_id}`

请求：

```json
{
  "content": "Updated content"
}
```

响应：

- `SessionState`

只读内部消息必须返回 `400`。

### `DELETE /api/sessions/{session_id}/messages/{message_id}`

响应：

- `SessionState`

只读内部消息必须返回 `400`。

### `POST /api/sessions/{session_id}/messages/{message_id}/rollback`

响应：

- `SessionState`

只读内部消息必须返回 `400`。

## 流式接口

### `POST /api/sessions/{session_id}/messages/stream`

请求示例：

```json
{
  "message": "Explain the repo workflow.",
  "system_prompt": "Be concise."
}
```

行为约束：

- `message` 必填
- `system_prompt` 可选
- user message 必须先持久化，再启动 workflow
- 返回值是 SSE

### `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

请求体：

```json
{}
```

行为约束：

- 目标是 assistant 时，后端需要找到对应 user turn
- 目标是 user 时，直接从该 user turn 重跑
- system message 不允许 regenerate
- 只读内部消息不允许 regenerate

## SSE 契约

前端依赖以下事件：

- `workflow`
- `record`
- `chunk`
- `done`
- `error`

### `workflow`

payload：

- `WorkflowSnapshot`

### `chunk`

payload 示例：

```json
{
  "delta": "partial text",
  "content": "full partial text"
}
```

### `done`

payload：

- `ChatResponse`

### `error`

payload 示例：

```json
{
  "detail": "Chat request failed: Missing API key."
}
```

### `record`

payload：

- `MessageRecord`

语义：

- live `plan / tool / think` 更新
- pending answer card 用它来流式更新 `Thoughts`
