from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PROMPT_DIR = Path(__file__).with_name("prompt_templates")


def default_system_prompt(
    *,
    available_skills: list[str] | tuple[str, ...] = (),
    available_tools: list[str] | tuple[str, ...] = (),
) -> str:
    """Render the shared session-level system prompt."""
    return _template("system").format(
        available_tools=", ".join(available_tools) or "(none)",
        available_skills=_skills_catalog(list(available_skills)),
    ).strip()


def tool_back_message(
    *,
    allow_retrieve: bool,
    available_tools: list[str] | tuple[str, ...] = (),
) -> dict[str, str]:
    """Build the runtime-only continuation prompt appended after each tool result."""
    return {
        "role": "user",
        "content": _template("tool_back").format(
            allow_retrieve="yes" if allow_retrieve else "no",
            available_tools=", ".join(available_tools) or "(none)",
        ).strip(),
    }


@lru_cache(maxsize=None)
def _template(name: str) -> str:
    """Load one workflow prompt template from YAML."""
    path = PROMPT_DIR / f"{name}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "content" not in payload:
        raise ValueError(f"Workflow prompt template '{path.name}' must contain a 'content' field.")
    return str(payload["content"])


def _skills_catalog(skills: list[str]) -> str:
    """Render the short skill catalog."""
    if not skills:
        return "(none)"
    return "\n".join(f"- {skill}" for skill in skills)
