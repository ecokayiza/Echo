# Architecture

## Layout

```text
Eco_RAG/
  eco_rag/            # reusable Python core
  apps/
    api/              # FastAPI backend
    web/              # React frontend scaffold
    desktop/          # Tauri scaffold
  memory/             # persistent runtime memory
  docs/
  tests/
  data/
  db/
```

## Boundaries

- `eco_rag/` holds reusable RAG logic and should stay UI-agnostic.
- `apps/api/` exposes HTTP and streaming interfaces for clients.
- `apps/web/` will contain the React chat interface.
- `apps/desktop/` will wrap the web client with Tauri for desktop distribution.
- `memory/` stores persistent chat history and future memory artifacts outside the package code.

## Current Workflow Direction

- `eco_rag/workflows/state.py` defines typed run status and step state.
- `eco_rag/tracing/` provides event streaming primitives.
- `eco_rag/chat/registry.py` is the first extension point for multiple chat-model providers.
- `eco_rag/chat/context_manager.py` now owns session memory with pluggable storage and memory-selection policy.
- `eco_rag/chat/FileMessageStore` persists sessions under `memory/chat_sessions/` by default.
