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
- `apps/web/` now includes a lightweight static chat UI served by FastAPI at `/ui/`.
- `eco_rag/workflows/state.py` adds typed workflow status so a frontend can track progress more cleanly.
- `eco_rag/chat/registry.py` is the first extension point for multiple chat-model providers.
- `eco_rag/chat/context_manager.py` now manages first-class sessions, message IDs, and session-level persistence.
- Chat history now persists on disk by default under `memory/chat_sessions/`.
- The development UI supports session create/select/delete plus per-message edit/delete/rollback/regenerate controls.

### Run

```bash
python -m uvicorn apps.api.app.main:app --reload
```

Then open `http://127.0.0.1:8000/ui/`.

Key API routes:

- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/messages`
- `PATCH /api/sessions/{session_id}/messages/{message_id}`
- `DELETE /api/sessions/{session_id}/messages/{message_id}`
- `POST /api/sessions/{session_id}/messages/{message_id}/rollback`
- `POST /api/sessions/{session_id}/messages/{message_id}/regenerate`

If Windows reports `Failed to canonicalize script path`, use:

```bash
python run_api.py
```

That fallback launcher skips auto-reload by default so it behaves more reliably on Windows wrappers.

### TODO
  - [x] Basic Indexing and API calls
  - [x] Chat Client and Prompt Management
  - [x] Flatten core package to `eco_rag/`
  - [x] Add app-layer scaffolding for API / web / desktop
  - [ ] Langraph flow control
  - [ ] Memory management and compression
  - [ ] Agentic stage(query) and web search interface
  - [ ] Self evaluation and iteration stage
