from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..config import Config


class WorkflowDraftStore:
    """Persist one resumable workflow draft per session."""

    def __init__(
        self,
        *,
        storage: dict[str, dict[str, Any]] | None = None,
        base_dir: str | Path | None = None,
    ):
        self.storage = storage
        self.base_dir = Path(base_dir or Config.WORKFLOW_DRAFT_DIR)
        if self.storage is None:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> dict[str, Any] | None:
        """Load the saved workflow draft for one session."""
        if self.storage is not None:
            payload = self.storage.get(session_id)
        else:
            path = self._file(session_id)
            payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return self._normalize(payload)

    def persist(
        self,
        session_id: str,
        *,
        user_message_id: str,
        state: dict[str, Any],
        snapshot: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write the current live workflow draft."""
        payload = self._normalize(
            {
                "session_id": session_id,
                "user_message_id": user_message_id,
                "state": state,
                "snapshot": snapshot,
                "records": records,
            }
        )
        if self.storage is not None:
            self.storage[session_id] = payload
        else:
            self._file(session_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def clear(self, session_id: str):
        """Delete the saved workflow draft for one session."""
        if self.storage is not None:
            self.storage.pop(session_id, None)
            return
        path = self._file(session_id)
        if path.exists():
            path.unlink()

    def _file(self, session_id: str) -> Path:
        prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._-") or "session"
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()[:10]
        return self.base_dir / f"{prefix}-{digest}.json"

    @staticmethod
    def _normalize(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        state = payload.get("state")
        snapshot = payload.get("snapshot")
        records = payload.get("records")
        if not isinstance(state, dict) or not isinstance(snapshot, dict) or not isinstance(records, list):
            return None
        user_message_id = str(payload.get("user_message_id") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id or not user_message_id:
            return None
        return {
            "session_id": session_id,
            "user_message_id": user_message_id,
            "state": state,
            "snapshot": snapshot,
            "records": [dict(item) for item in records if isinstance(item, dict)],
        }
