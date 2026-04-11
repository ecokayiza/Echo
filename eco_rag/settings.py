from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .config import Config


@dataclass(frozen=True)
class AppSettings:
    """Store the small set of runtime settings used by the app."""

    max_context_messages: int = 12
    max_retrieve_rounds: int = 2
    prompt_truncate_chars: int = 500


def normalize_app_settings(payload: dict | None = None) -> AppSettings:
    """Normalize partially configured settings into the runtime defaults."""
    data = payload if isinstance(payload, dict) else {}
    return AppSettings(
        max_context_messages=_positive_int(data.get("max_context_messages"), 12),
        max_retrieve_rounds=_positive_int(data.get("max_retrieve_rounds"), 2),
        prompt_truncate_chars=_positive_int(data.get("prompt_truncate_chars"), 500),
    )


def load_app_settings() -> AppSettings:
    """Load the root settings file and fall back to defaults when missing."""
    path = Config.SETTINGS_PATH
    if not path.exists():
        return AppSettings()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Settings file '{path.name}' must contain a JSON object.")
    return normalize_app_settings(payload)


def save_app_settings(settings: AppSettings | dict) -> AppSettings:
    """Persist the runtime settings document."""
    resolved = normalize_app_settings(asdict(settings) if isinstance(settings, AppSettings) else settings)
    Config.SETTINGS_PATH.write_text(json.dumps(asdict(resolved), ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved


def _positive_int(value: object, default: int) -> int:
    """Keep positive integer settings and fall back for everything else."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value if value > 0 else default
