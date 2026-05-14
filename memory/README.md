# Memory

这个目录放运行时持久化数据，目的是把对话和 live workflow 状态放在代码包外部，重启后仍然可恢复。

当前主要布局：

```text
memory/
├── chat_sessions/     # 已持久化的 session / message 历史
└── workflow_live/     # 每个 session 的 live workflow draft
```

## chat_sessions

`echo.chat.Sessions` 会把聊天历史写到这里。

当前 session 文件会保存：

- session 元信息
- 聚合 token usage
- 按顺序排列的消息记录

消息里可能包含：

- `role`
- `content`
- `message_type`
- `workflow_turn_id`
- `tool_name`
- `token_usage`

## workflow_live

`echo.workflow.WorkflowDraftStore` 会把可恢复的 live workflow draft 写到这里。

它用于：

- 中断后的同轮恢复
- 记录当前 `next_step`
- 保留当前 workflow state
- 保留 live snapshot
- 保留已产生但尚未写回 session history 的内部 records

## 上下文边界

很重要的一点：

- `chat_sessions/` 是下一轮长期上下文的来源
- `workflow_live/` 只是当前回合恢复用的临时草稿

换句话说：

- 下一轮模型不会直接读取 `workflow_live/`
- 只有最终落盘到 session history 的消息才算长期记忆
