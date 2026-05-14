# API 后端说明

这个目录是 Echo 的 FastAPI 后端入口。

主链路：

`FastAPI Route -> ChatService -> Session / Messages -> WorkflowService -> LangGraph -> Model / Tools`

更细的 workflow 设计见：

- [echo/workflow/README.md](../../echo/workflow/README.md)

## 后端负责什么

- 暴露 HTTP 与 SSE 接口
- 管理 session / message 持久化
- 管理 `models.json`
- 管理 `settings.json`
- 管理根目录 `databases.json`
- 管理 database 配置与 active database
- 运行 LangGraph workflow
- 流式推送 `Thoughts` 过程和最终答案

后端不负责：

- 托管 embedding 推理服务
- 提供内置 `/v1/embeddings`
- 在项目内运行本地 embedding model

所有 embedding model 都被视为外部 OpenAI 兼容 provider，只通过 `models.json` 配置。

## 入口

- [main.py](./app/main.py)

`create_app(...)` 会：

- 确保 database settings 存在
- 创建 `ChatService`
- 注册 session、message、database、model-settings 路由
- 在 `apps/web/dist` 存在时挂载 `/ui`

## 当前 Workflow 语义

固定节点：

- `plan`
- `retrieve`
- `tool`
- `think`
- `answer`

关键规则：

- `plan` / `think` 是唯一模型决策节点
- `retrieve` / `answer` 是内部控制节点
- `tool` 执行 MCP 工具：`load_skill`、`date`、`database_search`、`web_search`、`web_fetch` 和 `workspace_*`
- 运行时 memory 使用 flat transcript，完整保留当前回合的 `plan / tool / think / answer`
- workflow 结束后把真实内部记录写入 session history

最终会落盘：

- `system`
- `user`
- assistant `plan`
- zero or more `tool`
- zero or more assistant `think`
- assistant `answer`

## SSE 事件

聊天流式接口会发出这些事件：

- `workflow`
  - live workflow snapshot
- `record`
  - 一条内部 workflow 记录
- 例如 assistant `plan`、tool `tool`、assistant `think`、assistant `answer`
- `chunk`
  - 最终 `answer` 的增量文本
- `done`
  - 已持久化完成后的最终 session state
- `error`
  - 终止性错误

Web UI 用法：

- `record` 驱动 `Thoughts`
- `chunk` 驱动最终 answer 正文
- `workflow` 驱动右侧 live workflow panel

## 持久化与上下文

长期上下文来源只有 session history。

下一轮 `build_context()` 规则：

- 保留唯一 system prompt
- 排除 `tool`
- 同一 `workflow_turn_id` 会压缩成一条 assistant workflow context
- 保留可见的 `plan`、`think`、`answer` sections
- 排除 tool result bodies 和 provider `tool_calls`

运行中的恢复依赖：

- `memory/workflow_live/`

每个 session 只保留一个 live workflow draft，用来处理中断恢复。

## RAG 与 Database

database 和 embedding model 是一对一配对：

- 一个 database 只绑定一个 embedding model
- 该库的入库和检索都必须使用这个配对模型
- 检索时 query embedding 也由这个模型生成

当前 database 管理由这些接口提供：

- `GET /api/databases`
- `POST /api/databases`
- `PATCH /api/databases/{database_id}`
- `POST /api/databases/{database_id}/select`
- `DELETE /api/databases/{database_id}`

每个 database 返回：

- `id`
- `name`
- `collection_name`
- `embedding_model_name`
- `document_count`
- `created_at`
- `updated_at`

## Message 可变更边界

这些内部记录是只读的：

- `message_type == "plan"`
- `message_type == "think"`
- `message_type == "tool"`

不能：

- edit
- delete
- rollback
- regenerate

普通 `user` 和最终 `answer` 仍然允许正常操作。

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
- `PATCH /api/sessions/{session_id}/system-prompt`
- `DELETE /api/sessions/{session_id}`

聊天与消息：

- `POST /api/sessions/{session_id}/messages/stream`
- `PATCH /api/sessions/{session_id}/messages/{message_id}`
- `DELETE /api/sessions/{session_id}/messages/{message_id}`
- `POST /api/sessions/{session_id}/messages/{message_id}/rollback`
- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

数据库：

- `GET /api/databases`
- `POST /api/databases`
- `PATCH /api/databases/{database_id}`
- `POST /api/databases/{database_id}/select`
- `DELETE /api/databases/{database_id}`
