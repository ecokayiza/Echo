from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .date import date
from .database_search import database_search
from .skill_loader import load_skill
from .web_fetch import web_fetch
from .web_search import web_search
from .workspace_files import workspace_edit_file, workspace_list_files, workspace_read_file, workspace_write_file

ToolFunction = Callable[..., dict[str, Any]]

TOOL_FUNCTIONS: tuple[ToolFunction, ...] = (
    load_skill,
    date,
    database_search,
    web_search,
    web_fetch,
    workspace_list_files,
    workspace_read_file,
    workspace_write_file,
    workspace_edit_file,
)

TOOL_NAMES = tuple(function.__name__ for function in TOOL_FUNCTIONS)
