# 前后端接口契约

这份文档定义 `apps/web` 与 `apps/api` 之间的交互协议。

重点说明：

- 前端可以调用哪些接口
- 请求体和响应体结构
- SSE 事件格式
- session / message 行为规则
- workflow snapshot 的字段要求

## 适用范围

当前前端主路径包括：

- 读取元信息
- 列表 / 创建 / 选择 / 删除 session
- 更新 system prompt
- 编辑 / 删除 / 回滚消息
- 流式发送消息
- 流式重新生成消息

## 全局规则

- 所有普通 HTTP 请求和响应都使用 JSON。
- 所有时间使用 UTC ISO-8601 字符串。
- message `role` 只有三种：
  - `system`
  - `user`
  - `assistant`
- workflow 节点名固定为：
  - `plan`
  - `retrieve`
  - `think`
  - `answer`
- workflow 运行状态固定为：
  - `queued`
  - `running`
  - `completed`
  - `failed`
- 前端不会为后端补 workflow 字段；后端必须返回完整结构。

## 共享数据结构

### `TokenUsage`

```json
{
  "prompt_tokens": 120,
  "prompt_cache_hit_tokens": 64,
  "completion_tokens": 30,
  "total_tokens": 150
}
```

说明：

- 各字段可以按需缺省
- 但只要返回 usage，就必须使用这套字段名

### `SessionSummary`

```json
{
  "session_id": "session-123",
  "title": "天气对话",
  "created_at": "2026-04-02T09:00:00+00:00",
  "updated_at": "2026-04-02T09:05:00+00:00",
  "message_count": 3,
  "preview": "今天会比较暖和。",
  "token_usage": {
    "prompt_tokens": 123,
    "prompt_cache_hit_tokens": 64,
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
  "content": "今天会比较暖和。",
  "token_usage": {
    "prompt_tokens": 123,
    "prompt_cache_hit_tokens": 64,
    "completion_tokens": 27,
    "total_tokens": 150
  }
}
```

说明：

- `pending` 只是前端本地字段
- 后端不会返回 `pending`

### `SessionState`

```json
{
  "session": {
    "session_id": "session-123",
    "title": "天气对话",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 3,
    "preview": "今天会比较暖和。",
    "token_usage": {
      "prompt_tokens": 123,
      "prompt_cache_hit_tokens": 64,
      "completion_tokens": 27,
      "total_tokens": 150
    },
    "total_tokens": 150
  },
  "messages": [
    {
      "id": "message-1",
      "role": "system",
      "content": "请清晰、简洁地回答。"
    },
    {
      "id": "message-2",
      "role": "user",
      "content": "今天天气怎么样？"
    },
    {
      "id": "message-3",
      "role": "assistant",
      "content": "今天会比较暖和。",
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

约束：

- `session` 必须是完整的 `SessionSummary`
- `messages` 必须是完整、有序的消息列表

### `WorkflowNodeStatus`

```json
{
  "node": "plan",
  "status": "completed",
  "detail": "Planner chose the first action."
}
```

### `WorkflowLog`

```json
{
  "level": "info",
  "node": "plan",
  "message": "plan started."
}
```

### `WorkflowSnapshot`

```json
{
  "query": "今天天气怎么样？",
  "context_items": [],
  "answer": "今天会比较暖和。",
  "token_usage": {
    "prompt_tokens": 123,
    "prompt_cache_hit_tokens": 64,
    "completion_tokens": 27,
    "total_tokens": 150
  },
  "status": "completed",
  "active_node": null,
  "node_statuses": [
    { "node": "plan", "status": "completed", "detail": "可以直接开始推理。" },
    { "node": "retrieve", "status": "skipped", "detail": "这一路径不需要外部上下文。" },
    { "node": "think", "status": "completed", "detail": "当前上下文足以回答。" },
    { "node": "answer", "status": "completed", "detail": "已生成最终答案。" }
  ],
  "logs": [
    { "level": "info", "node": null, "message": "Workflow created." },
    { "level": "info", "node": "plan", "message": "plan started." }
  ],
  "errors": []
}
```

强约束：

- `node_statuses` 必须存在
- `node_statuses.length` 必须等于 `meta.workflow_steps.length`
- `logs` 必须存在
- `active_node` 必须存在；结束时可以为 `null`
- `status` 必须与当前 workflow 真实状态一致

### `ChatResponse`

```json
{
  "session": {
    "session_id": "session-123",
    "title": "天气对话",
    "created_at": "2026-04-02T09:00:00+00:00",
    "updated_at": "2026-04-02T09:05:00+00:00",
    "message_count": 3,
    "preview": "今天会比较暖和。",
    "token_usage": {
      "prompt_tokens": 123,
      "prompt_cache_hit_tokens": 64,
      "completion_tokens": 27,
      "total_tokens": 150
    },
    "total_tokens": 150
  },
  "messages": [
    {
      "id": "message-1",
      "role": "system",
      "content": "请清晰、简洁地回答。"
    },
    {
      "id": "message-2",
      "role": "user",
      "content": "今天天气怎么样？"
    },
    {
      "id": "message-3",
      "role": "assistant",
      "content": "今天会比较暖和。",
      "token_usage": {
        "prompt_tokens": 123,
        "prompt_cache_hit_tokens": 64,
        "completion_tokens": 27,
        "total_tokens": 150
      }
    }
  ],
  "reply": "今天会比较暖和。",
  "token_usage": {
    "prompt_tokens": 123,
    "prompt_cache_hit_tokens": 64,
    "completion_tokens": 27,
    "total_tokens": 150
  },
  "workflow": {
    "query": "今天天气怎么样？",
    "context_items": [],
    "answer": "今天会比较暖和。",
    "token_usage": {
      "prompt_tokens": 123,
      "prompt_cache_hit_tokens": 64,
      "completion_tokens": 27,
      "total_tokens": 150
    },
    "status": "completed",
    "active_node": null,
    "node_statuses": [
      { "node": "plan", "status": "completed", "detail": "可以直接开始推理。" },
      { "node": "retrieve", "status": "skipped", "detail": "这一路径不需要外部上下文。" },
      { "node": "think", "status": "completed", "detail": "当前上下文足以回答。" },
      { "node": "answer", "status": "completed", "detail": "已生成最终答案。" }
    ],
    "logs": [
      { "level": "info", "node": null, "message": "Workflow created." }
    ],
    "errors": []
  }
}
```

约束：

- `session` 和 `messages` 必须是最终、已持久化后的状态
- 顶层 `reply` 和顶层 `token_usage` 只表示“这一次新生成的 assistant 回复”
- `workflow` 表示这一轮对话对应的完整 workflow 结果

## HTTP 接口

### `GET /api/health`

用途：

- 检查后端是否可用
- 返回当前默认模型

响应示例：

```json
{
  "status": "ok",
  "model": "deepseek-chat"
}
```

### `GET /api/meta`

用途：

- 获取 workflow 枚举
- 获取默认 system prompt
- 获取默认模型设置

响应示例：

```json
{
  "workflow_statuses": ["queued", "running", "completed", "failed"],
  "workflow_steps": ["plan", "retrieve", "think", "answer"],
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

响应：

- `SessionSummary[]`

### `POST /api/sessions`

请求：

```json
{
  "title": "可选标题",
  "session_id": "可选自定义 id"
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
  "title": "新的会话标题"
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
  "content": "请直接、务实地回答。"
}
```

清空 system prompt：

```json
{
  "content": null
}
```

响应：

- `SessionState`

行为要求：

- 更新 system prompt 时，不得删除后续消息
- 清空 system prompt 时，必须保留剩余对话

### `PATCH /api/sessions/{session_id}/messages/{message_id}`

请求：

```json
{
  "content": "修改后的内容"
}
```

响应：

- `SessionState`

行为要求：

- 编辑普通消息时，不能裁掉后续消息
- 编辑 system message 等价于更新 system prompt

### `DELETE /api/sessions/{session_id}/messages/{message_id}`

响应：

- `SessionState`

行为要求：

- 删除 system message 时，只删除 system prompt
- 删除非 system message 时，从该消息开始截断分支

### `POST /api/sessions/{session_id}/messages/{message_id}/rollback`

响应：

- `SessionState`

行为要求：

- 保留目标消息
- 删除该消息之后的所有消息

## 主流式聊天接口

### `POST /api/sessions/{session_id}/messages/stream`

这是 UI 的主发送入口。

请求示例：

```json
{
  "message": "请简单解释什么是 RAG。",
  "system_prompt": "请简洁、务实地回答。",
  "settings": {
    "provider": "openai_compatible",
    "model": "deepseek-chat",
    "api_key": null,
    "base_url": "https://api.deepseek.com",
    "temperature": 0.7
  }
}
```

行为要求：

- `message` 必填
- `system_prompt` 可选
- 如果请求里带了 `system_prompt`，后端必须先更新 session，再追加 user message
- user message 必须先落盘，再启动 workflow
- 返回值是 SSE，不是普通 JSON

### `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

这是 UI 的主重生成入口。

请求示例：

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

行为要求：

- 目标是 assistant message 时，后端必须向前找到对应 user message
- 目标是 user message 时，从该点直接重跑
- system message 不允许重生成

## SSE 契约

前端依赖以下事件：

- `workflow`
- `chunk`
- `done`
- `error`

### `workflow`

payload：

- `WorkflowSnapshot`

用途：

- 更新 workflow 调试面板
- 更新状态栏
- 同步当前 node、日志和错误

### `chunk`

payload 示例：

```json
{
  "delta": "暖和",
  "content": "今天会比较暖和"
}
```

规则：

- `delta` 是本次新增文本
- `content` 是当前累计完整文本
- 前端用 `content` 覆盖 pending assistant 内容

### `done`

payload：

- `ChatResponse`

规则：

- 必须返回最终、已落盘的 session 状态
- 前端用它覆盖乐观 UI

### `error`

payload 示例：

```json
{
  "detail": "Chat request failed: Missing API key."
}
```

规则：

- 当前流式请求应视为失败
- 前端直接展示 `detail`

## 当前契约问题

- 前端严格依赖完整 workflow snapshot，所以后端改字段需要同步修改前端类型和渲染逻辑。
- `WorkflowSnapshot` 已经偏向“调试视图”而不是极简业务返回，这对开发期很有帮助，但也意味着后端 payload 设计必须保持稳定。
