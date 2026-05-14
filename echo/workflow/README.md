# Workflow 说明

这份文档描述 Echo 当前真实生效的 LangGraph workflow。

目标很简单：

- 保留 LangGraph 作为控制流编排层
- 让 `plan` 和 `think` 成为唯一模型决策节点
- 让 `retrieve` 和 `answer` 成为内部控制节点
- 让 `tool` 统一执行本地 MCP 工具
- 让当前回合使用一条 flat transcript memory
- 让 state、snapshot、live draft 都只保留必要字段

## 当前节点

固定节点顺序：

1. `plan`
2. `retrieve`
3. `tool`
4. `think`
5. `answer`

固定路由：

- `START -> plan | retrieve | tool | think | answer`
- `plan -> retrieve | answer`
- `retrieve -> tool`
- `tool -> think`
- `think -> retrieve | answer`
- `answer -> END`

`START` 支持 fresh run 和从 live draft 恢复。

## 节点职责

### `plan`

- 调用模型
- 读取当前 flat workflow memory
- 直接决定 `answer` 还是 `retrieve`
- 持久化一条 assistant 记录；如果同次决策包含 `<echo_answer>`，类型为 `answer`，否则为 `plan`

允许格式：

```text
<echo_plan>
...
</echo_plan>
<echo_answer>
...
</echo_answer>
```

或：

```text
<echo_plan>
...
</echo_plan>
provider-native tool call: web_search(...)
```

### `retrieve`

- 不调用模型
- 只验证上一跳准备好的 `pending_retrieve`
- 让 workflow panel 能显示“当前进入检索阶段”

不会写入聊天历史。

### `tool`

- 执行 `pending_retrieve`
- 支持 `load_skill(...)`
- 支持 `date(...)`
- 支持 `database_search(...)`
- 支持 `web_search(...)`
- 支持 `web_fetch(...)`
- 支持 `workspace_*` 文件工具
- 持久化一条 `role == "tool"` 的消息
- 把完整 tool 结果追加进 flat workflow memory
- 下一跳 `think` 直接读取最新的 `tool` 结果继续决策

### `think`

- 调用模型
- 读取包含完整 tool 结果的 flat workflow memory
- 决定继续 `retrieve` 还是进入 `answer`
- 持久化一条 assistant 记录；如果同次决策包含 `<echo_answer>`，类型为 `answer`，否则为 `think`

格式与 `plan` 对称，只是它能看到前面的 tool 结果。

### `answer`

- 不调用模型
- 只发布前一跳已经准备好的 `prepared_answer`
- 以 `chunk` 形式增量流式输出最终答案
- 不额外生成内部聊天记录

最终用户可见的 assistant `answer` 来自上一条包含 `<echo_answer>` 的 workflow 记录，不再额外生成一条重复消息。

## Prompt 结构

模板入口：

- [prompts.py](./prompts.py)

模板文件：

- [prompt_templates/system.yaml](./prompt_templates/system.yaml)

规则：

- session 中始终只保留一个 system prompt
- 检索必须走 provider-native tool calls
- 不兼容旧的 `<retrieve>` / `<echo_retrieve>` 文本协议

## Flat Workflow Memory

当前回合里，模型看到的是一条 flat transcript：

- session `system`
- 历史长上下文
- 当前 `user`
- 当前回合的 `plan`
- 当前回合的 `tool`
- 当前回合的 `think`
- 当前回合的 `answer`
- 后续重复的 `tool / think`

也就是说：

- `think` 会完整看到之前的 `plan`
- 多跳检索时，下一次 `think` 也会看到之前所有 `tool` 结果和 `think`

## State

状态定义见：

- [state.py](./state.py)

当前只保留这些必要字段：

- `workflow_turn_id`
- `query`
- `requested_skill`
- `next_step`
- `retrieve_round`
- `pending_retrieve`
- `prepared_answer`
- `workflow_memory`

## Snapshot 与 Logs

tracker 定义见：

- [tracker.py](./tracker.py)

live snapshot 只包含：

- `workflow_turn_id`
- `query`
- `answer`
- `status`
- `active_node`
- `tool_name`
- `node_statuses`
- `logs`
- `errors`

设计原则：

- snapshot 用于 live UI，不重复存整个节点输出
- 真实的 `plan / tool / think / answer` 内容由持久化 message 负责
- logs 保持最小，只留高信号信息

## 记录与 Streaming

workflow 对外发三类核心流：

- `state`
  - live workflow snapshot
- `record`
  - 一条内部记录
  - 例如 `plan`、`tool`、`think`、`answer`
- `chunk`
  - 最终 `answer` 的增量文本

chat 层会把它们适配成 API SSE：

- `workflow`
- `record`
- `chunk`
- `done`

## Live Draft 与恢复

live draft 定义见：

- [drafts.py](./drafts.py)

规则：

- 每个 session 只保留一个 live workflow draft
- 在 material event 后更新 draft
- 通过 `session_id + user_message_id` 恢复
- 命中同一轮用户消息时，从保存的 `next_step` 继续
- 命中不同用户消息时，旧 draft 会被清掉

## 持久化与下一轮 Context

长期记忆由：

- [echo/chat/context_manager.py](../chat/context_manager.py)

负责。

当前规则：

- 只有落盘的 session history 会进入下一轮长期上下文
- `tool` 不会进入下一轮 context
- 同一 `workflow_turn_id` 只保留一条 assistant 推理记录
- 优先最后一条 `think`
- 没有 `think` 时回退到 `plan`
- 同轮 `answer` 不再重复灌回下一轮 context
- 保留的 `plan / think` 会被裁剪成纯 reasoning block，不带 action block

## 当前会落盘哪些消息

一轮带检索的聊天最终会保存：

1. `user`
2. assistant `plan`
3. zero or more `tool`
4. zero or more assistant `think`
5. assistant `answer`

其中：

- `plan / think / tool` 是只读内部记录
- `answer` 是正常 assistant 回复

## 配置

运行时配置：

- [settings.json](../../settings.json)

当前只保留：

- `chunk_size`
- `chunk_overlap`
- `max_retrieve_rounds`
- `use_marker_pdf_loader`

模型配置：

- [models.json](../../models.json)

其中 embedding model 一律视为外部 OpenAI 兼容 provider。
