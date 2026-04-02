# Memory

Runtime memory lives here so it stays outside the code package and survives restarts.

Suggested layout:

```text
memory/
  chat_sessions/   # persisted chat histories
  artifacts/       # summaries, extracted facts, future long-term memory
```

`eco_rag.chat.Sessions` now reads and writes chat histories in `memory/chat_sessions/`.

Current persistence notes:

- Session files keep aggregate usage at the session root in `usage` so total usage survives reloads.
- Message and session usage keep the same four counters: `prompt_tokens`, `prompt_cache_hit_tokens`, `completion_tokens`, and `total_tokens`.
- The current code expects this format directly and does not keep backward-compat branches for older layouts.
