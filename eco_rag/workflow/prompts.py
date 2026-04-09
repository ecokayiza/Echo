from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROMPT_DIR = Path(__file__).with_name("prompt_templates")


def plan_messages(query: str, context: list[dict[str, Any]], tools_enabled: bool) -> list[dict[str, str]]:
    """Build the plan node messages from YAML templates."""
    allowed = ["retrieve", "think"] if tools_enabled else ["think"]
    template = _template("plan")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                allowed_next_steps=", ".join(allowed),
                tools_available="yes" if tools_enabled else "no",
                query=query,
                conversation_context=_conversation(context),
            ).strip(),
        },
    ]


def retrieve_messages(query: str, context_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build the retrieve node messages from YAML templates."""
    template = _template("retrieve")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                query=query,
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
    """Build the think node messages from YAML templates."""
    allowed = ["retrieve", "answer"] if allow_retrieve else ["answer"]
    template = _template("think")
    return [
        {"role": "system", "content": template["system"].strip()},
        {
            "role": "user",
            "content": template["user"].format(
                allowed_next_steps=", ".join(allowed),
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
    """Build the answer node messages from YAML templates."""
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
    """Format chat context for node prompts."""
    parts = []
    for item in messages:
        role = str(item.get("role", "user")).strip() or "user"
        content = str(item.get("content", "")).strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _context_items(items: list[dict[str, Any]]) -> str:
    """Format external context items for node prompts."""
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
    return "\n\n".join(parts)
