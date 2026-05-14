from __future__ import annotations

from typing import Any

from echo.skills import load_skill_document


def load_skill(skill_name: str) -> dict[str, Any]:
    """Load the full markdown instructions for one named skill."""
    resolved_name, content = load_skill_document(skill_name)
    return {
        "type": "skill",
        "skill_name": resolved_name,
        "content": content,
    }
