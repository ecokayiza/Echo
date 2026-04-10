from __future__ import annotations

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent
SKILLS_CATALOG_PATH = SKILLS_DIR / "skills.md"
SKILL_COMMAND_PATTERN = re.compile(r"^/skill\s+([A-Za-z0-9_-]+)(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)


def load_skill_catalog() -> str:
    """Return the skill summary injected before retrieval."""
    return SKILLS_CATALOG_PATH.read_text(encoding="utf-8").strip()


def list_available_skills() -> list[str]:
    """List all concrete skill document names."""
    return sorted(path.stem for path in SKILLS_DIR.glob("*.md") if path.name != SKILLS_CATALOG_PATH.name)


def load_skill_document(skill_name: str) -> tuple[str, str]:
    """Load one skill document and return the normalized name plus markdown."""
    normalized = _normalize_skill_name(skill_name)
    candidates = [
        normalized,
        normalized.replace("-", "_"),
        normalized.replace("_", "-"),
    ]
    for candidate in dict.fromkeys(candidates):
        path = SKILLS_DIR / f"{candidate}.md"
        if path.exists():
            return path.stem, path.read_text(encoding="utf-8").strip()
    available = ", ".join(list_available_skills()) or "none"
    raise ValueError(f"Unknown skill '{skill_name}'. Available skills: {available}.")


def extract_requested_skill(query: str) -> tuple[str | None, str]:
    """Extract `/skill name` from the user query and return the normalized skill plus remaining text."""
    cleaned = " ".join((query or "").strip().split())
    if not cleaned:
        return None, ""

    match = SKILL_COMMAND_PATTERN.match(cleaned)
    if match is None:
        return None, cleaned

    skill_name = _normalize_skill_name(match.group(1))
    remaining = " ".join((match.group(2) or "").strip().split())
    return skill_name or None, remaining or cleaned


def _normalize_skill_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", (value or "").strip().lower())
    return text.strip("_")
