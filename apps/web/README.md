# Eco_RAG Web UI

这个目录是 Eco_RAG 的 React 前端。它不是自己推理 workflow，而是消费后端持续推送的 workflow snapshot，并把聊天、历史会话和流程过程一起呈现出来。

## 技术栈

- React 19
- TypeScript
- Vite
- 原生 CSS
- REST + SSE

## 前端职责

- 渲染聊天工作台
- 管理 session 列表与选中状态
- 发送消息、重生成、编辑、删除、回滚
- 实时展示 workflow 节点状态、日志和过程 trace
- 展示已持久化的 assistant message workflow 数据
- 管理模型设置界面

前端不负责：

- workflow 路由决策
- tool / skill 选择
- token usage 计算
- session 底层持久化

## 关键目录

聊天组件：

- `src/components/chat/`

功能面板：

- `src/components/panels/`
  - `WorkflowPanel.tsx`
  - `WorkflowGraph.tsx`
  - `ModelSettingsPanel.tsx`

共享组件：

- `src/components/common/`

状态与副作用：

- `src/hooks/useChatWorkspace.ts`

数据适配与网络：

- `src/lib/api.ts`
- `src/lib/sse.ts`
- `src/lib/workflow.ts`
- `src/lib/storage.ts`

类型：

- `src/types/chat.ts`

## 主交互流

发送消息时：

1. `MessageComposer` 触发发送
2. `useChatWorkspace` 调用流式接口
3. `readEventStream(...)` 消费 SSE
4. `workflow` 事件更新工作流面板
5. `chunk` 事件更新 pending assistant message
6. `done` 事件用后端返回的已持久化 session 覆盖本地状态

## 当前依赖的 workflow 语义

前端默认后端 workflow 节点顺序是：

- `plan`
- `inject_skills`
- `retrieve`
- `think`
- `answer`

当前 snapshot 里最重要的字段包括：

- `status`
- `active_node`
- `node_statuses`
- `logs`
- `errors`
- `context_items`
- `loaded_skills`
- `trace`
- `answer`

其中：

- `trace` 保存本轮 `plan / retrieve / think / answer` 的模型输出
- `loaded_skills` 保存本轮按需载入的 skill
- 这些数据会挂在 assistant message 的 `workflow` 字段上

因此刷新或重新打开 session 时，前端可以从消息历史中恢复 workflow 过程，而不需要重新跑一遍模型。

## 会话恢复语义

前端现在同时处理两种 workflow 来源：

1. SSE 过程中的临时 workflow
2. session 历史中 assistant message 已持久化的 `workflow`

`useChatWorkspace` 优先相信后端已经持久化的 message workflow；只有在兼容旧数据时，才会把流式 `workflow` 补到最后一条 assistant message 上。

## 开发

安装依赖：

```bash
npm install
```

本地开发：

```bash
npm run dev
```

生产构建：

```bash
npm run build
```

## 依赖的后端能力

前端依赖：

- `GET /api/meta`
- `GET /api/health`
- `GET /api/model-settings`
- `PUT /api/model-settings`
- session CRUD
- `POST /api/sessions/{session_id}/messages/stream`
- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

完整契约请看：

- [apps/Contract.md](../Contract.md)
