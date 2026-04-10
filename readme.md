# Eco_RAG

Eco_RAG 是一个以聊天为唯一主入口的 LLM 应用。系统核心不是固定的“检索增强问答”流水线，而是一条用 LangGraph 编排的可观察 workflow：模型先规划路线，再按需注入 skills、调用 tools、反思是否继续检索，最后输出答案。

## 当前架构

- 后端：FastAPI
- 前端：React + TypeScript + Vite
- 聊天持久化：磁盘 session / message JSON
- 编排层：LangGraph workflow
- 检索与动作层：`eco_rag/tools/`
- 技能目录与文档：`eco_rag/skills/`

## 当前 workflow

真实流程已经重构为：

- `START -> plan`
- 快路径：`plan -> answer -> END`
- 多跳路径：`plan -> inject_skills -> retrieve -> think -> answer -> END`

多跳路径里的细节：

- `inject_skills` 会在进入 retrieve 前注入 `eco_rag/skills/skills.md`
- `retrieve` 由模型输出 JSON 指令决定是否调用工具
- 如果 `retrieve` 选择 `load_skill`，会回到 `retrieve`，且只允许一次额外 skill load
- 如果 `retrieve` 选择搜索类工具，例如 `database_search` 或 `web_search`，工具结果会写入 `context_items`，然后进入 `think`
- `think` 会输出 `conclusion / update_plan / self_reflection / next_step`
- 如果 `think` 认为还缺信息，可以再回到 `retrieve`，但有次数上限

详细说明见：

- [eco_rag/workflow/README.md](./eco_rag/workflow/README.md)

## Skills 与 Tools

当前约定很简单：

- 具体工具实现放在 `eco_rag/tools/`
- 具体 skill 文档放在 `eco_rag/skills/`
- `skills.md` 只放 skill 列表和大致说明
- skill 正文按需加载，不一次性塞进 prompt

默认检索相关能力包括：

- `database_search`
- `web_search`
- `load_skill`

如果外部还传入旧式 `tool_runner`，系统会自动包成兼容工具 `legacy_search`。

## 上下文与持久化

这里有一条很重要的边界：

- 只有 `context_manager` 管理并落盘的聊天消息，会作为下一轮的长期上下文
- 一轮 workflow 内的额外上下文，例如 `context_items`、节点 JSON 输出、trace、tool result summary，会一起落到 assistant message 的 `workflow` 字段里
- 这些 workflow 元数据会被 UI 用来回放过程，但不会通过 `build_context()` 回灌给下一轮模型

也就是说：

- chat history 是长期记忆
- workflow snapshot 是本轮过程记录

## 目录结构

```text
Eco_RAG/
├── eco_rag/
│   ├── chat/                  # session、message、模型调用、聊天服务
│   ├── workflow/              # LangGraph 图、状态、节点、追踪、提示词模板
│   ├── tools/                 # retrieve 阶段的工具
│   ├── skills/                # skills.md 与具体 skill 文档
│   ├── indexing/              # embedding / vector DB 支撑
│   ├── domain/                # 共享领域结构
│   └── config.py
├── apps/
│   ├── api/
│   ├── web/
│   └── Contract.md
├── memory/
│   └── chat_sessions/
├── tests/
├── models.json
└── pyproject.toml
```

## 主链路

一次聊天的真实调用顺序：

1. 前端调用 `POST /api/sessions/{session_id}/messages/stream`
2. `ChatService` 先写入 user message
3. `Messages.build_context()` 只提取长期聊天上下文
4. `WorkflowService` 构建本轮 LangGraph workflow
5. workflow 运行 `plan / inject_skills / retrieve / think / answer`
6. 后端持续推送 `workflow` 和 `chunk`
7. 完成后把 assistant message 和完整 workflow snapshot 一起落盘

## 运行

安装依赖：

```bash
python -m pip install -e .
```

前端开发：

```bash
cd apps/web
npm install
npm run dev
```

启动后端：

```bash
python -m uvicorn apps.api.app.main:app --reload
```

Windows 上如果脚本路径解析不稳定，也可以直接运行：

```bash
python run.py
```

## 文档索引

- [eco_rag/workflow/README.md](./eco_rag/workflow/README.md)
- [apps/api/README.md](./apps/api/README.md)
- [apps/web/README.md](./apps/web/README.md)
- [apps/Contract.md](./apps/Contract.md)
