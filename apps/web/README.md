# Eco_RAG Web UI

这个目录是 Eco_RAG 的 React 前端。

它不自己决定 workflow，只消费后端提供的 session history、SSE 事件和 database state。

## 技术栈

- React 19
- TypeScript
- Vite
- 原生 CSS
- REST + SSE

## 前端负责什么

- 渲染聊天工作台
- 管理 session 列表和当前会话
- 管理 database 列表和 active database
- 发送消息、重生成、编辑、删除、回滚
- 渲染 live workflow panel
- 在最终 answer 里重建 `Thoughts`
- 管理 model settings 和 database settings UI

前端不负责：

- workflow 决策
- tool 执行
- embedding 推理
- 向量检索逻辑
- session 持久化

## 当前流式交互

发送消息后，前端会同时消费三类关键流：

- `workflow`
  - 更新右侧 live workflow panel
- `record`
  - 把当前回合的 `plan / tool / think` 追加进 pending answer 的 `Thoughts`
- `chunk`
  - 增量更新最终 answer 文本

完成时：

- `done` 会返回已持久化的最终 session state
- 本地 pending UI 会被真实持久化消息替换

## 聊天区渲染规则

主聊天流只显示：

- `user`
- 最终 assistant `answer`

不会单独显示：

- `system`
- 原始 `plan`
- 原始 `think`
- 原始 `tool`

这些内部消息会按 `workflow_turn_id` 归组，然后显示到最终 answer card 的 `Thoughts` 中。

`Thoughts` 会显示：

- `plan` 的 reasoning block
- `think` 的 reasoning block
- tool 结果

`Thoughts` 不会显示：

- 内嵌的 `[answer]`
- `tool_back`
- routine workflow log spam

## Workflow 面板

右侧 `Workflow` 面板是 live 状态面板：

- 显示 `plan -> retrieve -> tool -> think -> answer` graph
- 中间 `tool` 节点会显示当前工具名
- 默认标签为 `</>`
- 下方 `Logs` 展示 workflow step detail 和高信号日志

历史流程回放不依赖这个面板，而是来自 answer card 里的 `Thoughts`。

## Database 面板

Session 列表下方有 database 面板：

- 选择 active database
- 显示数据库文档数
- 显示绑定的 embedding model
- 点击配置图标打开 database settings

当前 database settings 已支持：

- 创建 database
- 选择 database
- 重命名 database
- 删除 database

后续内容管理和更多 database 配置会继续扩展在这里。

## 关键目录

聊天组件：

- `src/components/chat/`

面板组件：

- `src/components/panels/`

状态与副作用：

- `src/hooks/useChatWorkspace.ts`

网络与适配：

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

接口契约可参考：

- [apps/Contract.md](../Contract.md)
