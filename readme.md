# Eco_RAG

Eco_RAG 是一个以聊天为主入口的可观察 LLM workspace。它不是“固定模板式 RAG”，而是一条由 LangGraph 控制的决策 workflow：模型先 `plan`，按需 `retrieve`，统一通过 `tool` 执行动作，再 `think` 是否继续，最后输出 `answer`。

## 当前架构

- 后端：FastAPI
- 前端：React + TypeScript + Vite
- 编排层：LangGraph
- 聊天持久化：磁盘 session JSON
- 检索工具：`eco_rag/tools/`
- skills 文档：`eco_rag/skills/`
- 向量库：按 database 管理，和 embedding model 一一配对

## 当前 Workflow

固定节点：

- `plan`
- `retrieve`
- `tool`
- `think`
- `answer`

关键规则：

- `plan` 和 `think` 是唯一会调用模型的决策节点
- `retrieve` 和 `answer` 是内部控制节点，不单独落盘聊天回复
- `tool` 统一执行 `load_skill`、`database_search`、`web_search`
- 运行时 memory 是一条 flat transcript，会把完整 `plan / tool / think` 串起来
- workflow 结束后，只把真实消息写入 session history

## Streaming 体验

Web UI 现在区分两条流：

- `record`
  - 实时推送内部 `plan / tool / think` 记录
  - 用来驱动 answer card 里的 `Thoughts`
- `chunk`
  - 实时推送最终 `answer`
  - Web UI 会边收边更新最终回复正文

右侧 `Workflow` 面板显示 live graph 和 logs；历史回放则来自同轮持久化的 `plan / tool / think / answer` 消息，不依赖额外 snapshot 落盘。

## RAG 与 Embedding

当前 RAG 约束很明确：

- 一个 database 只绑定一个 embedding model
- 该 database 的入库和检索都必须使用这同一个 embedding model
- embedding model 在本项目里一律视为外部 OpenAI 兼容 API
- 配置来源只有 `models.json`

这意味着：

- 本项目只负责数据准备、发 API 请求、保存向量库、执行检索
- 不在 `eco_rag/` 里托管 embedding 推理服务
- 如果你部署了本地 embedding 服务，只需要把它当成外部 provider 写进 `models.json`

## 持久化与上下文

长期记忆只有 session history：

- `memory/chat_sessions/`

live workflow 恢复草稿单独存放：

- `memory/workflow_live/`

下一轮上下文构建规则：

- 保留顶部唯一 system prompt
- 排除 `tool`
- 同一 `workflow_turn_id` 只保留一条 assistant 推理消息
- 优先最后一条 `think`
- 没有 `think` 时回退到 `plan`
- 同轮 `answer` 不再重复灌回下一轮 context

## 目录

```text
Eco_RAG/
├── apps/
│   ├── api/                  # FastAPI backend
│   ├── desktop/              # reserved shell
│   └── web/                  # React frontend
├── db/                       # vector database files
├── eco_rag/
│   ├── chat/                 # sessions, messages, chat service
│   ├── domain/               # shared schemas
│   ├── indexing/             # vector DB + embedding client integration
│   ├── skills/               # skills catalog and docs
│   ├── tools/                # retrieve tools
│   └── workflow/             # LangGraph graph, nodes, prompts, tracker
├── memory/
│   ├── chat_sessions/        # persisted sessions
│   └── workflow_live/        # resumable live workflow drafts
├── tests/
├── databases.json            # database registry and active selection
├── models.json               # chat / embedding provider settings
├── settings.json             # runtime workflow settings
└── run.py
```

## 快速开始

安装依赖：

```bash
conda activate llm
python -m pip install -e .
```

启动后端：

```bash
python -m uvicorn apps.api.app.main:app --reload
```

启动前端：

```bash
cd apps/web
npm install
npm run dev
```

Windows 上也可以直接：

```bash
python run.py
```

## 文档索引

- [apps/api/README.md](./apps/api/README.md)
- [apps/web/README.md](./apps/web/README.md)
- [eco_rag/workflow/README.md](./eco_rag/workflow/README.md)
- [memory/README.md](./memory/README.md)
