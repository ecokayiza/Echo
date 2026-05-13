from __future__ import annotations

from inspect import isawaitable
from typing import Any, Callable

from langchain_core.tools import BaseTool, tool

from .database_search import database_search
from .skill_loader import load_skill
from .web_fetch import web_fetch
from .web_search import web_search
from .workspace_files import workspace_edit_file, workspace_list_files, workspace_read_file, workspace_write_file

ToolRunner = Callable[[str], Any]


def build_retrieve_tools(tool_runner: ToolRunner | None = None) -> list[BaseTool]:
    """Build the tool set exposed to the workflow retrieve node."""
    tools: list[BaseTool] = [
        load_skill,
        database_search,
        web_search,
        web_fetch,
        workspace_list_files,
        workspace_read_file,
        workspace_write_file,
        workspace_edit_file,
    ]
    if tool_runner is not None:

        @tool
        async def legacy_search(query: str) -> dict[str, Any]:
            """Call the workflow's configured legacy retrieval function."""
            items = _normalize_items(await _resolve(tool_runner(query)))
            return {
                "type": "context",
                "skill_name": "legacy_search",
                "items": items,
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
