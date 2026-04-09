# Eco_RAG

Eco_RAG 是一个以聊天为唯一主入口的 LLM 应用工程。当前重点不是传统意义上的“检索问答”，而是围绕一条可观察、可扩展的 workflow 来组织对话决策、工具调用和最终回答。

当前实现包括：

- `FastAPI` 后端
- `React + TypeScript + Vite` 前端
- 基于磁盘的 session/message 持久化
- 统一的流式聊天入口
- 基于 LLM 决策的 workflow 节点流转

本项目当前明确优先：

- 代码尽量少
- 结构清晰
- 模块边界明确
- 不为旧结构做兼容性妥协

## 当前整体情况

- 聊天是 `session-first` 的。
- Web UI 只走流式聊天主路径。
- 每一轮真实聊天都进入同一条 workflow。
- 当前 workflow 节点是 `plan -> retrieve -> think -> answer`。
- 每个 node 的 prompt 模板都独立存放在 YAML 文件里。
- session 和记忆数据默认落盘到 `memory/chat_sessions/`。
- workflow 状态、节点运行情况、日志和错误会同步到 UI。

## 目录结构

```text
Eco_RAG/
├── eco_rag/
│   ├── chat/                  # 会话、消息、模型调用、聊天业务编排
│   ├── workflow/              # workflow 状态、节点、模板、服务、跟踪
│   ├── indexing/              # 历史索引/检索实验代码，当前不在主聊天链路
│   ├── domain/                # 共享领域结构
│   └── config.py              # 运行时配置
├── apps/
│   ├── api/                   # FastAPI 应用与后端文档
│   ├── web/                   # React 前端
│   ├── desktop/               # 预留的桌面壳层目录
│   └── Contract.md            # 前后端接口契约
├── memory/
│   ├── chat_sessions/         # session 持久化
│   └── artifacts/             # 预留给后续长期记忆/工具产物
├── tests/
├── docs/
├── data/
├── db/
├── run.py
└── pyproject.toml
```

## 唯一主链路

当前产品主路径只有这一条：

1. 前端调用 `POST /api/sessions/{session_id}/messages/stream`
2. API 路由进入 `ChatService.stream_message(...)`
3. `ChatService` 持久化 user message，并通过 `Sessions` 与 `Messages` 组织上下文
4. `ChatService` 调用 `WorkflowService.stream_chat(...)`
5. `WorkflowService` 依次推进 `plan / retrieve / think / answer`
6. 每个 node 都通过对应 YAML 模板让模型输出下一步决策
7. 后端持续向前端发送 `workflow` 和 `chunk`
8. 完成后写入 assistant message，并通过 `done` 返回最终 session 状态

这意味着：

- chat 不是 workflow 旁边的另一套逻辑
- workflow 就是 chat 本身
- 没有单独给 UI 用的第二条“run 调试入口”

## 核心模块

- `eco_rag/chat/context_manager.py`
  只保留 `Sessions` 和 `Messages` 两个核心类。`Sessions` 负责 session 文件和 summary，`Messages` 负责消息操作和上下文构建。
- `eco_rag/chat/service.py`
  聊天业务入口。负责 session 生命周期、system prompt、消息编辑/删除/回滚/重生成，以及 workflow 完成后的持久化。
- `eco_rag/chat/chat_model.py`
  统一模型调用方式，并把 token usage 归一成统一字段。
- `eco_rag/chat/registry.py`
  根据运行时设置创建模型实例。
- `eco_rag/workflow/service.py`
  workflow 执行入口。负责推进 node、流式输出、错误传播。
- `eco_rag/workflow/tracker.py`
  统一维护 workflow status、active node、node status、logs 和 errors。
- `eco_rag/workflow/nodes.py`
  每个 node 的实际逻辑和节点间的 LLM 路由判断。
- `eco_rag/workflow/prompts.py`
  加载 YAML 模板并组装消息。
- `apps/api/app/main.py`
  对外暴露 HTTP 与 SSE 接口。
- `apps/web/src/`
  对话 UI、session 管理、workflow 调试面板和模型设置界面。

## 运行方式

先构建前端：

```bash
cd apps/web
npm install
npm run build
```

再启动后端：

```bash
python -m uvicorn apps.api.app.main:app --reload
```

访问：

- UI：`http://127.0.0.1:8000/ui/`
- OpenAPI：`http://127.0.0.1:8000/docs`

如果在 Windows 上遇到 `Failed to canonicalize script path`，可以直接运行：

```bash
python run.py
```

## 文档分工

- 根目录 `README`：项目总览、主链路、目录结构、当前问题
- `apps/api/README.md`：后端内部模块、流程、接口入口、状态同步方式
- `apps/Contract.md`：前后端交接接口、字段约束、SSE 事件契约
- `apps/web/README.md`：前端结构、依赖的后端能力、开发方式

## 当前问题

- `eco_rag/workflow/graph.py` 已经有 LangGraph 的图定义，但当前主流式执行路径实际由 `WorkflowService` 手动推进 node，而不是直接把 LangGraph 作为运行时入口。这意味着 LangGraph 目前更多是在“描述允许边”，不是主执行引擎。
- `indexing/` 仍然存在，但当前 chat 主链路并不依赖它。它更像实验区，而不是现在的核心产品路径。
- 前端对 workflow snapshot 是严格依赖的。后端如果改字段名、漏字段，前端会直接出错，不会帮后端兜底。
