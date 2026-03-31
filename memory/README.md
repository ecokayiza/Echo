# Memory

Runtime memory lives here so it stays outside the code package and survives restarts.

Suggested layout:

```text
memory/
  chat_sessions/   # persisted chat histories
  artifacts/       # summaries, extracted facts, future long-term memory
```

`eco_rag.chat.FileMessageStore` writes chat histories into `memory/chat_sessions/`.
