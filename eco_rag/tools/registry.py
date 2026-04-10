from __future__ import annotations

from inspect import isawaitable
from typing import Any, Callable

from langchain_core.tools import BaseTool, tool

from .database_search import database_search
from .skill_loader import load_skill
from .web_search import web_search

ToolRunner = Callable[[str], Any]


def build_retrieve_tools(tool_runner: ToolRunner | None = None) -> list[BaseTool]:
    """Build the tool set exposed to the workflow retrieve node."""
    tools: list[BaseTool] = [load_skill, database_search, web_search]
    if tool_runner is not None:

        @tool
        async def legacy_search(query: str) -> dict[str, Any]:
            """Call the workflow's configured legacy retrieval function."""
            items = _normalize_items(await _resolve(tool_runner(query)))
            return {
                "type": "context",
                "skill_name": "legacy_search",
                "items": items,
                "query": " ".join((query or "").strip().split()),
                "count": len(items),
            }

        tools.append(legacy_search)
    return tools


async def _resolve(value: Any) -> Any:
    return await value if isawaitable(value) else value


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items or []:
        if hasattr(item, "model_dump"):
            normalized.append(item.model_dump())
        elif isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"content": str(item)})
    return normalized
