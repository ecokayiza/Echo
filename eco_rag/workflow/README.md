# Workflow 说明

这份文档描述 Eco_RAG 当前真实生效的 LangGraph workflow。

当前设计目标很简单：

- 保留 LangGraph 作为流程编排层
- 让 `plan` 和 `think` 成为唯一的模型决策节点
- 让 `retrieve` 和 `answer` 成为可显示但不持久化聊天回复的内部节点
- 让 `tool` 成为统一的技能加载和检索执行节点
- 让运行中的 workflow 使用一条 flat transcript memory 串起多轮 `plan / tool / think`
- 保持 state、snapshot、live draft 都尽量精简

## 当前节点

固定节点顺序：

1. `plan`
2. `retrieve`
3. `tool`
4. `think`
5. `answer`

固定路由：

- `START -> plan | retrieve | tool | think | answer`
  - 用于 fresh run 或 resume
- `plan -> retrieve | answer`
- `retrieve -> tool`
- `tool -> think`
- `think -> retrieve | answer`
- `answer -> END`

## 每个节点的职责

### `plan`

职责：

- 读取 flat workflow memory
- 决定这轮是直接结束还是先进入检索
- 在同一次回复里同时给出决策和最终答案或检索指令

输出格式只允许 bracketed text：

```text
[plan]
...
[next]
answer
[answer]
...
```

或：

```text
[plan]
...
[next]
retrieve
[retrieve]
web_search("...")
```

`plan` 的输出会作为 assistant message 持久化，`message_type == "plan"`。

### `retrieve`

职责：

- 不调用模型
- 只验证上一跳 `plan` 或 `think` 准备好的 `pending_retrieve`
- 让 workflow 面板里能明确显示“现在进入检索阶段”

它是内部控制节点，不会写入聊天历史。

### `tool`

职责：

- 执行 `pending_retrieve`
- 支持 `load_skill(...)`、`database_search(...)`、`web_search(...)`
- 兼容 `legacy_search(...)`
- 把完整 tool 结果写入持久化 `tool` message
- 同时把 tool 结果和 runtime-only `tool_back` prompt 追加到 flat workflow memory

`tool` 会持久化一条 `role == "tool"` 的消息，字段包括：

- `message_type == "tool"`
- `workflow_turn_id`
- `tool_name`

### `think`

职责：

- 读取已经积累的 flat workflow memory
- 判断是否继续 `retrieve`
- 或直接给出最终 `[answer]`

它和 `plan` 是对称节点，区别只有一个：

- `think` 比 `plan` 多看到了前面所有完整 `tool` 结果

输出格式：

```text
[think]
...
[next]
answer
[answer]
...
```

或：

```text
[think]
...
[next]
retrieve
[retrieve]
load_skill("database_search")
```

`think` 的输出会作为 assistant message 持久化，`message_type == "think"`。

### `answer`

职责：

- 不再调用模型
- 只把前一跳已经准备好的 `prepared_answer` 通过 stream 输出
- 结束 workflow

它是内部控制节点，不会额外生成一条内部记录。

最终用户可见的 assistant 回复由 chat 层在 workflow 完成后统一落盘，`message_type == "answer"`。

## 当前可用工具

工具注册入口：

- [eco_rag/tools/registry.py](../tools/registry.py)

当前 retrieve tools：

- `load_skill`
- `database_search`
- `web_search`
- `legacy_search`
  - 仅在 `WorkflowService(tool_runner=...)` 被传入旧式检索函数时出现

解析规则在：

- [nodes.py](./nodes.py)

retrieve block 只接受安全的简单函数调用，不接受 provider-native tool calls。

## Prompt 结构

Prompt 组装入口：

- [prompts.py](./prompts.py)

模板：

- [prompt_templates/system.yaml](./prompt_templates/system.yaml)
- [prompt_templates/tool_back.yaml](./prompt_templates/tool_back.yaml)

当前约束：

- session 里只保留一个 system prompt，并始终放在最上面
- 第一次模型决策走 `plan`，tool 之后的继续决策走 `think`
- 不允许 provider-native tool calls
- `tool_back` 只在运行时注入，不会落盘
- 一个共享的 `prompt_truncate_chars` 控制文本截断

## Workflow State

状态定义：

- [state.py](./state.py)

当前保留的必要字段：

- `workflow_turn_id`
- `query`
- `requested_skill`
- `next_step`
- `retrieve_round`
- `pending_retrieve`
- `prepared_answer`
- `workflow_memory`

设计原则：

- state 服务于“继续往下跑这一轮”
- 聊天历史服务于“下一轮长期上下文”
- 不在 tracker 里重复保存完整节点输出

## Snapshot 与 Tracker

tracker 定义：

- [tracker.py](./tracker.py)

当前 snapshot 只包含：

- `workflow_turn_id`
- `query`
- `answer`
- `status`
- `active_node`
- `node_statuses`
- `logs`
- `errors`

它不再保存：

- `trace`
- `workflow_memory`
- 重复的节点 payload

这些内容的来源已经分开：

- 内部消息记录保存 `plan / tool / think`
- workflow state 只保留继续执行所需的数据

## Live Draft 与恢复

live draft 定义：

- [drafts.py](./drafts.py)

规则：

- 每个 session 只保留一个 live workflow draft
- 在这些时刻更新 draft：
  - `plan` 完成
  - `retrieve` 接受 pending command
  - `tool` 完成
  - `think` 完成
  - `answer` 完成
- 恢复时按 `session_id + user_message_id` 匹配
- 命中同一轮 user message 时，从保存的 `next_step` 继续
- 命中不同 user message 时，旧 draft 会被清掉

## 聊天历史与上下文

聊天历史由：

- [eco_rag/chat/context_manager.py](../chat/context_manager.py)

负责。

当前规则：

- 只有落盘 session history 才是下一轮长期记忆
- `tool` 消息不会进入下一轮模型上下文
- 同一 `workflow_turn_id` 只保留一条 assistant 推理消息进入下一轮 context
  - 优先最后一条 `think`
  - 否则使用 `plan`
- 同轮 `answer` 不再进入下一轮 context
- 进入下一轮 context 的 `plan / think` 会被裁剪为纯 reasoning block，不带 `[next]` / `[retrieve]` / `[answer]`

也就是说，下一轮模型会看到上一轮 assistant 的最终推理结论，但不会直接看到 tool payload，也不会重复看到同轮 answer。

## Session 中实际保存什么

一轮带检索的聊天最终会保存这些消息：

1. user
2. assistant `plan`
3. zero or more `tool`
4. zero or more assistant `think`
5. assistant `answer`

其中：

- `plan / think / tool` 是只读内部记录
- `answer` 是正常 assistant 回复

## 配置

运行时配置在根目录：

- [settings.json](../../settings.json)

当前只保留需要的三个字段：

- `max_context_messages`
- `max_retrieve_rounds`
- `prompt_truncate_chars`

模型配置仍然在：

- [models.json](../../models.json)

## 主要入口文件

- [graph.py](./graph.py)
- [nodes.py](./nodes.py)
- [service.py](./service.py)
- [tracker.py](./tracker.py)
- [drafts.py](./drafts.py)
- [prompts.py](./prompts.py)

## 当前实现的核心边界

- LangGraph 负责控制流，不负责长期记忆
- `plan` / `think` 负责决策，不直接执行工具
- `retrieve` / `answer` 负责阶段控制，不产生持久化聊天回复
- `tool` 负责执行外部动作，并把结果转成 state 与内部消息
- session history 是下一轮上下文来源
- live draft 是中断恢复来源
