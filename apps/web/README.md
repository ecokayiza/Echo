# Eco_RAG Web UI

这个目录是 Eco_RAG 的 React 前端。

它不自己推理 workflow，只消费后端返回的：

- session history
- live workflow snapshot
- SSE `chunk`
- database state

## 技术栈

- React 19
- TypeScript
- Vite
- 原生 CSS
- REST + SSE

## 前端负责什么

- 渲染聊天工作台
- 管理 session 列表与当前会话
- 管理 database 列表与当前激活库
- 发送消息、重生成、编辑、删除、回滚
- 渲染 live workflow 面板
- 把同轮 `plan / tool / think` 重建到最终 answer 的 `Thoughts`
- 展示模型设置与数据库设置界面

前端不负责：

- workflow 决策
- tool 执行
- embedding 生成
- 向量检索逻辑
- skill 选择
- session 底层持久化

## 当前依赖的 workflow 语义

前端依赖后端固定节点顺序：

- `plan`
- `retrieve`
- `tool`
- `think`
- `answer`

最重要的 live snapshot 字段：

- `workflow_turn_id`
- `query`
- `answer`
- `status`
- `active_node`
- `node_statuses`
- `logs`
- `errors`

历史消息里会包含：

- assistant `plan`
- tool `tool`
- assistant `think`
- assistant `answer`

但主聊天流的渲染规则是：

- 隐藏原始 `plan / think / tool` 气泡
- 只显示最终 `answer`
- 在这个 `answer` 卡片里，用同轮消息重建 `Thoughts`

`Thoughts` 只显示：

- `plan` 的 reasoning block
- `think` 的 reasoning block
- tool 结果

不会显示：

- `[next]`
- 原始嵌入式 `[answer]`
- `tool_back`
- routine workflow log spam

## 数据库面板

左侧栏在 session 列表下方有数据库面板：

- 选择 active database
- 显示当前库的文档数
- 显示当前库绑定的 embedding model
- 点击配置图标打开 database settings modal

当前 database settings modal 已支持：

- 创建数据库
- 选择数据库
- 重命名数据库
- 删除数据库

后续内容管理和更细的数据库参数会继续放在这个区域扩展。

## 主交互流

发送消息时：

1. `MessageComposer` 触发发送
2. `useChatWorkspace` 调用流式接口
3. `readEventStream(...)` 消费 SSE
4. `workflow` 事件更新右侧 live workflow 面板
5. `chunk` 事件更新 pending answer
6. `done` 事件用后端返回的已持久化 session 状态覆盖本地状态

## 会话恢复语义

前端恢复 workflow 的来源分成两部分：

1. live 运行时
   - 来自 SSE 的 `workflow` snapshot
2. 历史回放
   - 来自 session messages 里的 `plan / tool / think / answer`

也就是说：

- 右侧 workflow panel 是 live 状态面板
- 历史上的流程回放由 answer card 的 `Thoughts` 负责
- 不再依赖持久化到 answer message 上的 workflow snapshot

## 关键目录

聊天组件：

- `src/components/chat/`

面板组件：

- `src/components/panels/`
  - `WorkflowPanel.tsx`
  - `WorkflowGraph.tsx`
  - `ModelSettingsPanel.tsx`
  - `DatabasePanel.tsx`
  - `DatabaseSettingsModal.tsx`

状态与副作用：

- `src/hooks/useChatWorkspace.ts`

数据适配与网络：

- `src/lib/api.ts`
- `src/lib/sse.ts`
- `src/lib/workflow.ts`
- `src/lib/storage.ts`

类型：

- `src/types/chat.ts`

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

完整接口契约：

- [apps/Contract.md](../Contract.md)
