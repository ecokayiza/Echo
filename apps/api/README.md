# API App

This directory hosts the FastAPI backend entrypoint.

Suggested local run command:

```bash
python -m uvicorn apps.api.app.main:app --reload
```

After startup:
- `http://127.0.0.1:8000/ui/` serves the lightweight chat frontend
- `http://127.0.0.1:8000/api/health` checks backend status
- `http://127.0.0.1:8000/api/sessions` lists and creates sessions
- `http://127.0.0.1:8000/api/sessions/{session_id}/messages` sends chat turns
