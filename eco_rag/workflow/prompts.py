from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..skills import DEFAULT_SKILLS, load_skill_document

PROMPT_DIR = Path(__file__).with_name("prompt_templates")
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def default_system_prompt(
    *,
    available_skills: list[str] | tuple[str, ...] = (),
    available_tools: list[str] | tuple[str, ...] = (),
) -> str:
    """Render the shared session-level system prompt."""
    return _template("system").format(
        default_skills=_default_skill_documents(),
        available_skills=_available_skills_document(list(available_skills)),
    ).strip()


@lru_cache(maxsize=None)
def _template(name: str) -> str:
    """Load one workflow prompt template from YAML."""
    path = PROMPT_DIR / f"{name}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "content" not in payload:
        raise ValueError(f"Workflow prompt template '{path.name}' must contain a 'content' field.")
    return str(payload["content"])


@lru_cache(maxsize=None)
def _default_skill_documents() -> str:
    """Render the bundled markdown for all default skills."""
    documents = []
    for skill_name in DEFAULT_SKILLS:
        _, content = load_skill_document(skill_name)
        if content.strip():
            documents.append(content.strip())
    return "\n\n".join(documents) if documents else "(none)"


@lru_cache(maxsize=None)
def _skills_catalog_document() -> str:
    """Render the shared skills index markdown."""
    path = SKILLS_DIR / "skills.md"
    if not path.exists():
        return "(none)"
    return path.read_text(encoding="utf-8").strip() or "(none)"


def _available_skills_document(skills: list[str]) -> str:
    """Render the skills index, appending any discovered extras if needed."""
    catalog = _skills_catalog_document()
    extras = [skill for skill in skills if f"`{skill}`" not in catalog]
    if not extras:
        return catalog
    extra_lines = "\n".join(f"- `{skill}`" for skill in extras)
    return f"{catalog}\n\nAdditional discovered skills:\n{extra_lines}".strip()
