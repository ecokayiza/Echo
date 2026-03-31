## Eco_RAG

> Trying to build a well-structured and efficient RAG system (Personal practice).

### Overview

##### structure of the Eco_RAG system:
```
Eco_RAG/
├── eco_rag/                # reusable Python core package
│   ├── config.py
│   ├── domain/
│   ├── chat/
│   ├── indexing/
│   ├── tracing/
│   └── workflows/
├── apps/
│   ├── api/                # FastAPI backend entrypoint
│   ├── web/                # React frontend scaffold
│   └── desktop/            # Tauri desktop scaffold
├── memory/                 # persistent runtime memory
├── docs/
├── tests/
├── data/                   # datasets or PDFs
├── db/                     # vector DB storage
├── .env                    # API keys and secrets (never commit this)
└── pyproject.toml
```

##### Flow
![alt text](assets/image.png)

### Notes

- `eco_rag/` now stays framework-agnostic and is the shared logic layer.
- `apps/api/` is the only backend-facing app layer for future streaming and orchestration endpoints.
- `apps/web/` and `apps/desktop/` are intentionally light scaffolds for the next frontend step.
- `eco_rag/workflows/state.py` adds typed workflow status so a frontend can track progress more cleanly.
- `eco_rag/chat/registry.py` is the first extension point for multiple chat-model providers.
- `eco_rag/chat/context_manager.py` provides simple session memory now, with swappable storage and memory policy later.
- Chat history now persists on disk by default under `memory/chat_sessions/`.

### TODO
  - [x] Basic Indexing and API calls
  - [x] Chat Client and Prompt Management
  - [x] Flatten core package to `eco_rag/`
  - [x] Add app-layer scaffolding for API / web / desktop
  - [ ] Langraph flow control
  - [ ] Memory management and compression
  - [ ] Agentic stage(query) and web search interface
  - [ ] Self evaluation and iteration stage
