# Web App

This directory currently contains a lightweight static frontend served by FastAPI at `/ui/`.

Current files:

- `index.html`: layout
- `styles.css`: styling
- `app.js`: chat client logic

This keeps the project usable right now without introducing a full frontend build step. It can later be replaced by a React app using the same session-first API contract:

- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/messages`
- `PATCH/DELETE /api/sessions/{session_id}/messages/{message_id}`
