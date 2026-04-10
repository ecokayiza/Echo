from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROMPT_DIR = Path(__file__).with_name("prompt_templates")


def plan_messages(
    query: str,
    context: list[dict[str, Any]],
    retrieval_enabled: bool,
    requested_skill: str | None,
) -> list[dict[str, str]]:
    """Build the planner prompt."""
    allowed = ["answer", "retrieve"] if retrieval_enabled else ["answer"]
    template = _template("plan")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                allowed_next_steps=", ".join(allowed),
                tools_available="yes" if retrieval_enabled else "no",
                requested_skill=requested_skill or "(none)",
                query=query,
                conversation_context=_conversation(context),
            ).strip(),
        },
    ]


def retrieve_messages(
    query: str,
    context: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    skills_prompt: str,
    loaded_skills: list[dict[str, Any]],
    available_tools: list[str],
    requested_skill: str | None,
    can_load_skill: bool,
) -> list[dict[str, str]]:
    """Build the retrieve prompt."""
    template = _template("retrieve")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                query=query,
                conversation_context=_conversation(context),
                available_tools=", ".join(available_tools) or "(none)",
                requested_skill=requested_skill or "(none)",
                can_load_skill="yes" if can_load_skill else "no",
                skills_prompt=skills_prompt or "(skills catalog unavailable)",
                loaded_skills=_loaded_skills(loaded_skills),
                context_items=_context_items(context_items),
            ).strip(),
        },
    ]


def think_messages(
    query: str,
    context: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    allow_retrieve: bool,
) -> list[dict[str, str]]:
    """Build the reflection prompt."""
    allowed = ["retrieve", "answer"] if allow_retrieve else ["answer"]
    template = _template("think")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                allowed_next_steps=", ".join(allowed),
                allow_retrieve="yes" if allow_retrieve else "no",
                query=query,
                conversation_context=_conversation(context),
                context_items=_context_items(context_items),
            ).strip(),
        },
    ]


def answer_messages(
    query: str,
    context: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    system_prompt: str,
) -> list[dict[str, str]]:
    """Build the answer prompt."""
    template = _template("answer")
    base = [dict(message) for message in context]
    insert_at = next((index for index, item in enumerate(base) if item.get("role") != "system"), len(base))
    base.insert(
        0,
        {
            "role": "system",
            "content": template["system"].format(base_assistant_policy=system_prompt).strip(),
        },
    )
    base.insert(
        insert_at + 1,
        {
            "role": "system",
            "content": template["context"].format(
                query=query,
                context_items=_context_items(context_items),
            ).strip(),
        },
    )
    return base


@lru_cache(maxsize=None)
def _template(name: str) -> dict[str, str]:
    """Load one workflow prompt template from YAML."""
    path = PROMPT_DIR / f"{name}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Workflow prompt template '{path.name}' must be a mapping.")
    return {key: str(value) for key, value in payload.items()}


def _conversation(messages: list[dict[str, Any]]) -> str:
    """Format chat context for prompt injection."""
    parts = []
    for item in messages:
        role = str(item.get("role", "user")).strip() or "user"
        content = str(item.get("content", "")).strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts) or "(none)"


def _context_items(items: list[dict[str, Any]]) -> str:
    """Format external context items for prompt injection."""
    parts = []
    for index, item in enumerate(items, start=1):
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", item.get("document", ""))).strip()
        if not content:
            continue
        prefix = f"[{index}]"
        if title:
            prefix = f"{prefix} {title}"
        parts.append(f"{prefix}\n{content}")
    return "\n\n".join(parts) or "(none)"


def _loaded_skills(items: list[dict[str, Any]]) -> str:
    """Format loaded skill documents for prompt injection."""
    parts = []
    for skill in items:
        name = str(skill.get("name", "")).strip()
        content = str(skill.get("content", "")).strip()
        if not name or not content:
            continue
        parts.append(f"## {name}\n{content}")
    return "\n\n".join(parts) or "(none)"
