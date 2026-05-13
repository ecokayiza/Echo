from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .config import Config


@dataclass(frozen=True)
class AppSettings:
    """Store the small set of runtime settings used by the app."""

    chunk_size: int = Config.CHUNK_SIZE
    chunk_overlap: int = Config.CHUNK_OVERLAP
    max_retrieve_rounds: int = 10
    use_marker_pdf_loader: bool = True
    web_search_backend: str = "auto"
    enabled_skills: list[str] | None = None
    default_skills: list[str] | None = None


def normalize_app_settings(payload: dict | None = None) -> AppSettings:
    """Normalize partially configured settings into the runtime defaults."""
    data = payload if isinstance(payload, dict) else {}
    chunk_size = _positive_int(data.get("chunk_size"), Config.CHUNK_SIZE)
    chunk_overlap = min(_non_negative_int(data.get("chunk_overlap"), Config.CHUNK_OVERLAP), max(chunk_size - 1, 0))
    return AppSettings(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_retrieve_rounds=_positive_int(data.get("max_retrieve_rounds"), 10),
        use_marker_pdf_loader=_bool(data.get("use_marker_pdf_loader"), True),
        web_search_backend=_web_search_backend(data.get("web_search_backend")),
        enabled_skills=_optional_skill_list(data.get("enabled_skills")),
        default_skills=_optional_skill_list(data.get("default_skills")),
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


def _non_negative_int(value: object, default: int) -> int:
    """Keep zero or positive integer settings and fall back for everything else."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value if value >= 0 else default


def _bool(value: object, default: bool) -> bool:
    """Keep explicit boolean settings and fall back for everything else."""
    return value if isinstance(value, bool) else default


def _web_search_backend(value: object) -> str:
    """Normalize the selected free web-search backend."""
    if not isinstance(value, str):
        return "auto"
    cleaned = value.strip().lower()
    aliases = {"ddg": "duckduckgo", "duck": "duckduckgo", "baidu_search": "baidu", "bing_rss": "bing"}
    resolved = aliases.get(cleaned, cleaned)
    return resolved if resolved in {"auto", "duckduckgo", "bing", "baidu"} else "auto"


def _optional_skill_list(value: object) -> list[str] | None:
    """Keep explicit skill-name lists while preserving missing/null defaults."""
    if value is None:
        return None
    if not isinstance(value, list):
        return None

    skills: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        skills.append(cleaned)
    return skills
