# API 后端说明

这个目录对应 Eco_RAG 的 FastAPI 后端。

当前主链路：

`FastAPI Route -> ChatService -> Session / Messages -> WorkflowService -> LangGraph -> Model / Tools`

更细的 workflow 设计见：

- [eco_rag/workflow/README.md](../../eco_rag/workflow/README.md)

前后端契约见：

- [apps/Contract.md](../Contract.md)

## 后端负责什么

- 暴露 HTTP 与 SSE 接口
- 管理 session / message 持久化
- 读取与保存 `models.json`
- 读取与保存 `settings.json`
- 维护数据库配置 `memory/databases.json`
- 运行 LangGraph workflow
- 推送 live workflow 状态和最终答案流
- 管理指向外部 embedding provider 的配置

## 应用入口

- [main.py](./app/main.py)

`create_app(...)` 会：

- 确保至少存在一个数据库配置
- 创建 FastAPI 应用
- 注入 `ChatService`
- 注册 session、message、database、model-settings 路由
- 在前端构建产物存在时挂载 `/ui`

## 当前 workflow 语义

当前节点固定为：

- `plan`
- `retrieve`
- `tool`
- `think`
- `answer`

关键规则：

- `plan` 和 `think` 是唯一模型决策节点
- `retrieve` 和 `answer` 是内部控制节点，不持久化聊天回复
- `tool` 执行 `load_skill` / `database_search` / `web_search`
- workflow 运行时使用 flat transcript memory，把完整 `plan / tool / think` 串起来
- workflow 结束后只把真实消息写入 session history，不把 workflow snapshot 挂到 message 上

## RAG 与数据库

当前后端把“向量库”和“embedding 模型”绑定成一对：

- 一个 database 只对应一个 embedding model
- 一个 database 里的内容只应该由它自己的 embedding model 建库
- `database_search` 检索时也只使用这个配对模型生成 query embedding

数据库配置保存在：

- `memory/databases.json`

默认推荐的本地 embedding 模型：

- `Qwen/Qwen3-Embedding-0.6B`

模型会下载到：

- `models/Qwen3-Embedding-0.6B`

## Embedding 服务边界

主 API 不托管 embedding 模型，也不提供 `/v1/embeddings`。

当前约定是：

- 所有 embedding model 都被视为外部 OpenAI 兼容 provider
- `models.json` 是唯一来源，负责保存它们的 `model / api_key / base_url`
- 主项目只负责数据准备、发请求、保存向量库和检索

如果你要本地部署 Qwen3 embedding 服务，脚本放在：

- [models/qwen3_embedding_service.py](../../models/qwen3_embedding_service.py)

它是独立服务，不由 `apps/api` 托管。

建议把 `models.json` 里的 embedding `base_url` 指向：

- `http://127.0.0.1:8091/v1`

## SSE 事件

前端依赖四种事件：

- `workflow`
- `chunk`
- `done`
- `error`

含义：

- `workflow`：当前 live workflow snapshot
- `chunk`：最终 `answer` 的增量文本
- `done`：已持久化的最终 session 状态
- `error`：终止性错误

## 持久化边界

后端现在显式区分两类数据：

1. 长期聊天历史
   - 保存在 session messages 中
   - 会进入下一轮 `build_context()`
2. 回合内 live workflow 状态
   - 只通过 SSE `workflow` 和 live draft 管理
   - 不会持久化到 message 的 `workflow` 字段

一轮消息最终会落盘：

- `system`
- `user`
- assistant `plan`
- zero or more `tool`
- zero or more assistant `think`
- assistant `answer`

下一轮上下文只保留同轮最后一条推理消息：

- 优先最后一条 `think`
- 否则使用 `plan`
- 不包含 `tool`
- 不重复包含同轮 `answer`

## Read-only 消息

这些内部消息在 API 上是只读的：

- `message_type == "plan"`
- `message_type == "think"`
- `message_type == "tool"`

它们不能：

- edit
- delete
- rollback
- regenerate

普通 `user` / 最终 `answer` 消息仍然允许正常操作。

## 数据库接口

- `GET /api/databases`
- `POST /api/databases`
- `PATCH /api/databases/{database_id}`
- `POST /api/databases/{database_id}/select`
- `DELETE /api/databases/{database_id}`

返回当前 database 列表、active database，以及每个库的：

- `id`
- `name`
- `collection_name`
- `embedding_model_name`
- `document_count`

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

## 默认工具

retrieve tools 定义在：

- [eco_rag/tools](../../eco_rag/tools)

默认包含：

- `load_skill`
- `database_search`
- `web_search`

兼容层：

- `legacy_search`
  - 只在 `WorkflowService(tool_runner=...)` 被提供时出现
