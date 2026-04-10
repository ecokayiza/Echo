# Workflow 说明

这份文档专门解释 Eco_RAG 当前真实生效的 workflow。重点是四件事：

- 当前 LangGraph 图到底怎么走
- `skills.md`、skill 文档、tools 是怎么协作的
- workflow state / trace / snapshot 保存了什么
- 以后要扩展 skill 或 tool 应该改哪里

## 设计目标

这个 workflow 不是传统的固定 RAG。

它解决的是一轮聊天里的三个问题：

1. 现在能不能直接回答
2. 如果不能，应该加载什么 skill 或调用什么工具
3. 外部动作做完以后，是继续检索还是该结束

所以当前图的核心不是“先检索再回答”，而是“先规划，再按需行动，再反思是否继续行动”。

## 当前图

外层图定义在：

- [graph.py](./graph.py)

当前固定节点：

1. `plan`
2. `inject_skills`
3. `retrieve`
4. `think`
5. `answer`

当前边关系：

- `START -> plan`
- `plan -> answer`
- `plan -> inject_skills`
- `inject_skills -> retrieve`
- `retrieve -> retrieve`
- `retrieve -> think`
- `think -> retrieve`
- `think -> answer`
- `answer -> END`

可以把它理解成两条主路径。

快路径：

```text
START -> plan -> answer -> END
```

多跳路径：

```text
START -> plan -> inject_skills -> retrieve
retrieve -> retrieve   # 只用于 load_skill 触发的额外一跳
retrieve -> think
think -> retrieve      # 继续搜证据，有限次
think -> answer
answer -> END
```

## 节点职责

### `plan`

职责：

- 看 query 和聊天上下文
- 决定是直接回答还是进入检索
- 不生成最终答案

输出契约：

```json
{
  "next_step": "answer | retrieve",
  "reason": "..."
}
```

特殊规则：

- 如果用户输入了 `/skill name`，`plan` 仍然会走模型，但最终路由会被约束为 `retrieve`

### `inject_skills`

职责：

- 在进入 retrieve 前把 `eco_rag/skills/skills.md` 注入到状态里
- 如果用户显式输入了 `/skill name`，在这里直接预加载该 skill 文档

这个节点不调用模型。

它的价值是把两层信息拆开：

- `skills.md` 只放目录和用途摘要
- 具体 skill 正文按需加载

### `retrieve`

职责：

- 让模型决定这一步要不要调用工具
- 执行至多一个工具动作
- 把 tool result 写回 workflow state
- 决定下一步是继续 `retrieve` 还是进入 `think`

这是当前 workflow 的核心节点。

与旧实现的区别：

- 现在不再保留 retrieve 内部的嵌套 LangGraph 子图
- 每次 `retrieve` 都对应一次明确的模型输出
- 工具调用由 `retrieve` 节点自己按 JSON 指令执行

输出契约：

```json
{
  "next_step": "retrieve | think",
  "reason": "...",
  "tool_name": "load_skill | database_search | web_search | legacy_search | null",
  "tool_args": {}
}
```

路由规则是固定的：

- `tool_name == "load_skill"` 时，下一步一定是 `retrieve`
- 搜索类工具执行完后，下一步一定是 `think`
- 不调用工具时，也会进入 `think`

### `think`

职责：

- 基于当前 `context_items` 和聊天上下文做一次反思
- 判断是否还需要再 retrieve 一次
- 如果证据已经足够，则进入 `answer`

输出契约：

```json
{
  "next_step": "retrieve | answer",
  "reason": "...",
  "conclusion": "...",
  "update_plan": "...",
  "self_reflection": "..."
}
```

这一步明确要求模型给出：

- 当前结论
- 下一步计划
- 自我反思

所以 `think` 不只是“要不要搜”，而是一个可回放的中间决策节点。

### `answer`

职责：

- 使用聊天上下文和 `context_items` 生成最终回复
- 通过 LangGraph custom stream 向外发送 `chunk`

它不调用工具，只负责最终回答。

## Skills 机制

skill 目录：

- [eco_rag/skills](../skills)

当前约定：

- `skills.md` 是目录，不是完整手册
- 目录里列出 skill 名称和大致说明
- 具体 skill 文档放在 `*.md`
- skill 正文只在真正需要时加载

默认会出现在 `skills.md` 的能力包括：

- `database_search`
- `web_search`

虽然它们本身也是“skill”，但默认已经在目录里可见，不需要先猜测名字。

## `/skill name` 的行为

如果用户输入：

```text
/skill web_search 帮我查一下最新的 LangGraph 教程
```

workflow 会做这几件事：

1. `new_state()` 解析出 `requested_skill = "web_search"`
2. `query` 会被清洗成实际问题文本
3. `plan` 会被强制约束到 `retrieve`
4. `inject_skills` 会直接预加载 `web_search.md`
5. 后续 `retrieve` 可以在已加载的 skill 基础上继续决定是否调用工具

也就是说，`/skill` 是显式注入入口，不需要模型先自己猜测该 skill。

## Tools 机制

工具实现目录：

- [eco_rag/tools](../tools)

默认注册逻辑：

- [registry.py](../tools/registry.py)

当前默认工具：

- `load_skill`
- `database_search`
- `web_search`

兼容工具：

- `legacy_search`
  - 仅当 `WorkflowService(tool_runner=...)` 被传入旧式检索函数时才出现

### `load_skill`

实现：

- [skill_loader.py](../tools/skill_loader.py)

返回结构：

```json
{
  "type": "skill",
  "skill_name": "...",
  "content": "..."
}
```

workflow 会把这类结果写入 `loaded_skills`。

### `database_search`

实现：

- [database_search.py](../tools/database_search.py)

职责：

- 使用 embedding 模型向量化 query
- 查询本地向量数据库
- 返回可被 workflow 采纳的 `context_items`

返回结构：

```json
{
  "type": "context",
  "skill_name": "database_search",
  "items": [...]
}
```

### `web_search`

实现：

- [web_search.py](../tools/web_search.py)

当前实现已经修正为：

- 解析 DuckDuckGo HTML 搜索结果页
- 抽取标题、摘要和 URL
- 不再使用对普通网页搜索基本不可用的 Instant Answer API

这意味着 `web_search` 现在能真正返回常规网页结果，而不是大多数时候只给空列表。

## Prompt 注入顺序

prompt 由：

- [prompts.py](./prompts.py)
- [prompt_templates](./prompt_templates)

统一组装。

当前顺序是：

1. `plan` 看聊天上下文和显式 skill 请求
2. 如果进入检索，`inject_skills` 先把 `skills.md` 注入状态
3. `retrieve` 再看到：
   - query
   - 会话上下文
   - `skills.md`
   - 已加载 skill
   - 已有 `context_items`
   - 可用工具列表
4. `think` 基于当前证据做反思
5. `answer` 用最终证据回答

这样做的好处是：

- 避免把所有 skill 正文一次性塞进 prompt
- 也避免模型完全不知道有哪些 skill

## State 结构

状态定义在：

- [state.py](./state.py)

当前关键字段：

- `query`
  - 当前用户问题，已经去掉 `/skill xxx` 命令壳
- `context`
  - 当前回合可见的聊天上下文
- `requested_skill`
  - 用户显式请求的 skill
- `next_step`
  - 下一个节点
- `retrieve_count`
  - 实际检索轮次数
- `skill_load_count`
  - `load_skill` 额外回路次数
- `skills_prompt`
  - 注入后的 `skills.md`
- `loaded_skills`
  - 已加载 skill 正文
- `context_items`
  - tool 返回的结构化证据
- `trace`
  - 每个模型节点的输出记录
- `answer`
  - 最终答案
- `token_usage`
  - 整轮 workflow 聚合 token

这里最重要的两个计数器：

- `skill_load_count`
  - 只控制 `load_skill -> retrieve` 这一类回路，默认只允许一次
- `retrieve_count`
  - 控制 `think -> retrieve` 的继续搜证据次数

所以“加载 skill”预算和“继续检索”预算是分开的。

## Trace 与 Snapshot

workflow 对 UI 暴露的 snapshot 由：

- [tracker.py](./tracker.py)

生成。

当前 snapshot 主要包含：

- `query`
- `requested_skill`
- `loaded_skills`
- `context_items`
- `trace`
- `answer`
- `token_usage`
- `status`
- `active_node`
- `node_statuses`
- `logs`
- `errors`

其中 `trace` 会记录：

- `plan` 的 JSON 输出
- 每次 `retrieve` 的 JSON 输出
- `retrieve` 的 tool result summary
- `think` 的 JSON 输出
- `answer` 的最终文本

这让前端在重新加载历史会话时，不需要重跑 workflow，也能回放本轮过程。

## 长期上下文 vs workflow 过程

这是当前设计里最重要的边界。

长期上下文：

- 来自 `context_manager` 管理的聊天消息
- 会进入下一轮 `build_context()`

workflow 过程：

- 来自 assistant message 的 `workflow` 字段
- 包括 `trace`、`context_items`、`loaded_skills`、日志、错误、节点状态
- 会落盘，供 UI 加载和回放
- 不会作为下一轮模型的长期上下文

换句话说：

- chat history 是长期记忆
- workflow snapshot 是回合内过程记录

## 运行时约束

默认约束在：

- [nodes.py](./nodes.py)
- [service.py](./service.py)

当前默认值：

- `max_retrieve_count = 2`
- `max_skill_loads = 1`

含义：

- `think -> retrieve` 最多再走两轮
- `load_skill -> retrieve` 最多额外走一轮

## 如何新增一个 tool

推荐顺序：

1. 在 `eco_rag/tools/` 下新增工具文件
2. 返回稳定的结构化字典
3. 在 [registry.py](../tools/registry.py) 注册
4. 如果模型需要理解该工具的使用时机，再补一个 skill 文档
5. 在 `skills.md` 加上摘要
6. 补 workflow 单测

## 如何新增一个 skill

推荐顺序：

1. 在 `eco_rag/skills/` 下新增 `your_skill.md`
2. 在 `skills.md` 里写一条简短说明
3. 如果它对应真实动作，确保存在对应 tool
4. 必要时补 `/skill your_skill ...` 路径测试

## 当前实现的优点

- 每个关键节点都有独立模型输出，易观察、易调试
- `/skill` 显式注入和模型自主 `load_skill` 同时支持
- `web_search` 和 `database_search` 都走统一 tool 接口
- workflow 过程可持久化、可回放，但不会污染长期上下文
- 结构足够简单，后续继续扩展不会被嵌套子图拖复杂度
