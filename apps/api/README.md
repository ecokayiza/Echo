# API 后端说明

这个目录对应 Eco_RAG 的 FastAPI 后端。后端的职责是把 session、workflow、模型配置和流式响应串成一条稳定的聊天主链路。

详细 workflow 设计见：

- [eco_rag/workflow/README.md](../../eco_rag/workflow/README.md)

接口契约见：

- [apps/Contract.md](../Contract.md)

## 后端负责什么

- HTTP 与 SSE 路由
- session / message 持久化
- `models.json` 读取与保存
- LangGraph workflow 执行
- workflow snapshot 实时推送
- assistant 回复与 token usage 落盘

## 应用入口

入口文件：

- [main.py](./app/main.py)

`create_app(...)` 会：

- 创建 FastAPI 应用
- 注入 `ChatService`
- 注册 session、message、model-settings、meta 路由
- 在前端构建产物存在时挂载 `/ui`

## 主要接口

系统与配置：

- `GET /api/health`
- `GET /api/meta`
- `GET /api/model-settings`
- `PUT /api/model-settings`

Session：

- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}`
- `PATCH /api/sessions/{session_id}`
- `DELETE /api/sessions/{session_id}`

聊天与消息：

- `POST /api/sessions/{session_id}/messages/stream`
- `PATCH /api/sessions/{session_id}/messages/{message_id}`
- `DELETE /api/sessions/{session_id}/messages/{message_id}`
- `POST /api/sessions/{session_id}/messages/{message_id}/rollback`
- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

## 流式聊天主链路

一次正常聊天的后端调用顺序：

1. 路由接收 `POST /api/sessions/{session_id}/messages/stream`
2. `ChatService.stream_message(...)` 持久化 user message
3. `Messages.build_context()` 构造长期聊天上下文
4. `WorkflowService.stream_chat(...)` 构建并运行 LangGraph workflow
5. workflow 输出 `workflow` 状态事件和 `chunk` 文本增量
6. 结束后把 assistant message 和 workflow snapshot 一起写回 session

可以简化理解为：

`FastAPI Route -> ChatService -> Sessions / Messages -> WorkflowService -> LangGraph -> Model / Tools`

## 当前 workflow 在后端里的真实形态

当前外层节点固定为：

- `plan`
- `inject_skills`
- `retrieve`
- `think`
- `answer`

当前边关系为：

- `plan -> answer | inject_skills`
- `inject_skills -> retrieve`
- `retrieve -> retrieve | think`
- `think -> retrieve | answer`
- `answer -> end`

这意味着：

- `plan` 决定是直接回答还是进入检索
- `inject_skills` 在 retrieve 之前注入 `skills.md`
- `retrieve` 由模型输出 JSON 决定是否调用工具
- `load_skill` 会触发一次 `retrieve -> retrieve`
- 搜索类工具执行完后统一进入 `think`
- `think` 再判断是否继续 retrieve 或直接 answer

## SSE 事件

前端依赖的 SSE 事件有四种：

- `workflow`
- `chunk`
- `done`
- `error`

其中：

- `workflow` 是完整 workflow snapshot
- `chunk` 是 answer 节点的增量输出
- `done` 是已持久化的最终聊天结果
- `error` 是终止性异常

## 持久化语义

后端现在区分两类数据：

1. 长期聊天上下文
   - 来自 session 中的 `messages`
   - 会进入后续回合的 `build_context()`
2. workflow 过程数据
   - 来自 assistant message 的 `workflow` 字段
   - 包括 `trace`、`context_items`、`loaded_skills`、节点状态、日志、错误等
   - 会持久化给 UI 回放，但不会重新喂给下一轮模型

这个边界是当前后端设计里最重要的约束之一。

## 后端模块划分

Route Layer：

- [main.py](./app/main.py)

Chat Layer：

- [context_manager.py](../../eco_rag/chat/context_manager.py)
- [service.py](../../eco_rag/chat/service.py)
- [registry.py](../../eco_rag/chat/registry.py)
- [chat_model.py](../../eco_rag/chat/chat_model.py)

Workflow Layer：

- [service.py](../../eco_rag/workflow/service.py)
- [graph.py](../../eco_rag/workflow/graph.py)
- [nodes.py](../../eco_rag/workflow/nodes.py)
- [prompts.py](../../eco_rag/workflow/prompts.py)
- [tracker.py](../../eco_rag/workflow/tracker.py)
- [state.py](../../eco_rag/workflow/state.py)

Tools / Skills：

- [eco_rag/tools](../../eco_rag/tools)
- [eco_rag/skills](../../eco_rag/skills)

## 当前默认工具

retrieve 默认注册：

- `load_skill`
- `database_search`
- `web_search`

兼容层：

- `legacy_search`
  - 只有 `WorkflowService(tool_runner=...)` 被传入旧式检索函数时才会出现

其中 `web_search` 已经改成解析 DuckDuckGo HTML 搜索结果页，而不是使用几乎拿不到普通搜索结果的 Instant Answer API。
