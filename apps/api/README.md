# API 后端说明

这个目录对应 Eco_RAG 的 FastAPI 后端。

这份文档只写后端内部情况，重点说明：

- 模块划分
- 主入口
- 真实调用关系
- workflow 的状态同步方式
- 存储责任
- 当前明确问题

前后端字段和接口契约请看 [apps/Contract.md](/c:/Users/22638/Desktop/design/Eco_RAG/apps/Contract.md)。

## 后端负责什么

后端负责：

- HTTP 与 SSE 路由
- session 和 message 持久化
- 模型配置解析与实例创建
- workflow 执行
- workflow 状态同步给前端
- assistant 回复与 token 使用量落盘

后端不负责：

- 前端状态拼装
- 前端乐观渲染
- 桌面壳层逻辑

## 主入口

后端应用入口：

- `apps/api/app/main.py`

当前唯一主聊天入口：

- `POST /api/sessions/{session_id}/messages/stream`

当前唯一主重生成入口：

- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

说明：

- 当前 Web UI 只走流式接口
- 同步聊天接口已经移除
- session 和 message 的管理接口仍然保留普通 HTTP 形式

## 后端模块划分

### Route Layer

- `apps/api/app/main.py`
  定义 FastAPI 路由、请求模型、SSE 包装和静态资源挂载。

### Chat Layer

- `eco_rag/chat/context_manager.py`
  只保留 `Sessions` 与 `Messages` 两个核心类。
- `eco_rag/chat/service.py`
  面向 API 的聊天业务层。
- `eco_rag/chat/registry.py`
  根据运行时设置创建模型实例。
- `eco_rag/chat/chat_model.py`
  统一模型调用方式与 token usage 结构。

### Workflow Layer

- `eco_rag/workflow/service.py`
  workflow 的实际运行入口。
- `eco_rag/workflow/tracker.py`
  统一管理 workflow status、active node、node status、logs 和 errors。
- `eco_rag/workflow/nodes.py`
  node 逻辑和 LLM 路由判断。
- `eco_rag/workflow/prompts.py`
  加载 YAML 模板并组装提示词消息。
- `eco_rag/workflow/prompt_templates/*.yaml`
  每个 node 一份独立模板。
- `eco_rag/workflow/graph.py`
  维护 LangGraph 图定义和允许边。
- `eco_rag/workflow/state.py`
  workflow 运行状态与共享字段定义。

### Storage Layer

- `memory/chat_sessions/*.json`
  session 元数据、消息列表和 session 级 usage 的落盘位置。

## 模块之间的调用关系

一次正常的流式聊天调用关系如下：

1. `main.py` 接收 `POST /api/sessions/{session_id}/messages/stream`
2. 路由调用 `ChatService.stream_message(...)`
3. `ChatService` 通过 `Sessions` 与 `Messages` 更新 session 和记忆
4. `ChatService` 调用 `WorkflowService.stream_chat(...)`
5. `WorkflowService` 调用 LangGraph 运行 workflow
6. LangGraph 按图路由执行各个 node
7. node 通过 `prompts.py` 加载 YAML 模板
8. node 通过 `chat/registry.py` 创建模型
9. 模型返回结构化决策或最终回答
10. `WorkflowTracker` 生成面向 UI 的 workflow snapshot
11. `ChatService` 把 workflow 结果写回 session，并输出 `done`

可以简化理解为：

`Route -> ChatService -> Sessions / Messages -> WorkflowService -> LangGraph -> Nodes -> Model`

## `Sessions` 与 `Messages`

### `Sessions`

`Sessions` 负责：

- session 文件路径映射
- session 读取与创建
- session summary 生成
- title 更新
- session 级 usage 聚合
- session 删除和持久化

### `Messages`

`Messages` 负责：

- 消息列表读取
- 上下文窗口构建
- 新增 assistant / user message
- 统一消息操作入口 `apply(...)`

当前消息操作包括：

- `edit`
- `delete`
- `rollback`
- `system_prompt`

说明：

- `send` 和 `regenerate` 不是单纯消息层动作，它们会进入 workflow，所以由 `ChatService` 负责
- `Messages` 只维护消息结构和上下文，不负责 workflow 运行

## Workflow 设计

当前 workflow 节点固定为：

- `plan`
- `retrieve`
- `think`
- `answer`

允许的路由关系：

- `plan -> retrieve | think`
- `retrieve -> think | answer`
- `think -> retrieve | answer`
- `answer -> end`

关键点：

- 允许边定义在 `graph.py`
- LangGraph 现在就是唯一运行时执行路径
- 实际走哪条边，由 node 的 LLM 输出 `next_step`
- 后端会严格校验 `next_step`
- 没有 fallback
- 模型输出非法时直接报错

## Prompt 模板

每个 node 都有独立 YAML 模板：

- `eco_rag/workflow/prompt_templates/plan.yaml`
- `eco_rag/workflow/prompt_templates/retrieve.yaml`
- `eco_rag/workflow/prompt_templates/think.yaml`
- `eco_rag/workflow/prompt_templates/answer.yaml`

这些模板的作用不是“重写查询”，而是：

- 让模型确认当前 node 应该做什么
- 判断下一步该去哪个 node
- 在 `answer` 阶段组织最终回答

这点很重要：

- 当前项目不是传统“先改写 query，再检索，再回答”的固定 RAG 管线
- `retrieve` 只是当前存在的一种外部上下文动作
- 后续真正的扩展方向应该放在 `tools/`，让 workflow 决定是否调用工具，而不是把系统绑死在检索上

## 流式状态同步

前端依赖后端发送四种 SSE 事件：

- `workflow`
- `chunk`
- `done`
- `error`

其中：

- `workflow` 对应一份完整 workflow snapshot
- `chunk` 对应当前回答增量
- `done` 对应最终、已落盘的聊天结果
- `error` 对应终止性错误

当前 workflow snapshot 由 `WorkflowTracker` 统一生成，包含：

- `status`
- `active_node`
- `node_statuses`
- `logs`
- `errors`
- `query`
- `context_items`
- `answer`
- `token_usage`

这样 UI 可以同时看到：

- 当前跑到哪个 node
- 每个 node 的完成/失败/跳过情况
- 路由日志
- 错误信息

## 存储

session 文件保存在 `memory/chat_sessions/`。

存储原则：

- 一个 session 一个文件
- session 根级保存聚合后的 `usage`
- assistant message 在可用时保存本条消息的 `token_usage`
- 不保留旧格式兼容逻辑

字段命名说明：

- 磁盘文件使用 `usage`
- API 返回使用 `token_usage`

## 当前明确问题

- `retrieve` 当前仍然是 workflow 中唯一真正落地的外部动作。对于一个强调“行动决策”的系统来说，这还不够，后续需要引入真正的 `tools/` 设计。
- 前端严格依赖 workflow snapshot 的字段完整性。后端一旦改字段名或漏字段，前端会直接失败。
