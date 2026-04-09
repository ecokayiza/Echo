# Web 前端说明

这个目录是 Eco_RAG 的 React 前端。

当前技术栈：

- React 19
- TypeScript
- Vite

## 前端负责什么

前端负责：

- session 列表和切换
- 聊天消息展示
- system prompt 编辑
- 模型设置编辑
- 发送 / 重生成消息
- workflow 调试面板
- 流式回答渲染

前端不负责：

- workflow 路由判断
- session 持久化
- token 聚合计算
- 工具调用决策

这些都由后端负责。

## 主交互路径

前端的主发送路径只有一条：

- `POST /api/sessions/{session_id}/messages/stream`

主重生成路径：

- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate/stream`

前端会消费以下 SSE 事件：

- `workflow`
- `chunk`
- `done`
- `error`

## 本地开发

```bash
cd apps/web
npm install
npm run dev
```

开发地址：

- `http://127.0.0.1:5173/ui/`

说明：

- Vite 配置了 `base: /ui/`
- 这样开发路径和 FastAPI 挂载路径保持一致

## 生产构建

```bash
cd apps/web
npm run build
```

构建产物输出到：

- `apps/web/dist/`

后端会把该目录挂载到：

- `/ui/`

## 接口依赖

完整接口和字段定义请看：

- [apps/Contract.md](/c:/Users/22638/Desktop/design/Eco_RAG/apps/Contract.md)

前端依赖的是流式接口，不依赖同步聊天接口。

## 当前前端约束

- workflow snapshot 会被严格校验
- 后端少字段、字段名变化、节点名变化，前端都会直接出错
- `pending` 是纯前端临时状态，不属于后端协议

## 当前问题

- workflow 面板现在已经能看状态、节点、日志和错误，但它仍然是开发期调试视图，信息密度高于普通产品界面。
- 当前 UI 已经不再把系统理解成“文档检索问答”，但部分视觉语言仍然偏开发工具风格，后续可以继续收敛。
