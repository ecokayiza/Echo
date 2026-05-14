from __future__ import annotations

import inspect
import sys
from contextlib import redirect_stdout
from functools import wraps
from typing import Any

from mcp.server.fastmcp import FastMCP

from .tools.registry import TOOL_FUNCTIONS

mcp = FastMCP("Echo Tools", log_level="ERROR")

def _stdio_safe_tool(tool_function):
    """Keep tool/library prints off stdout, which is reserved for MCP JSON-RPC."""
    signature = inspect.signature(tool_function)

    if inspect.iscoroutinefunction(tool_function):

        @wraps(tool_function)
        async def async_wrapper(*args: Any, **kwargs: Any):
            with redirect_stdout(sys.stderr):
                return await tool_function(*args, **kwargs)

        async_wrapper.__signature__ = signature
        return async_wrapper

    @wraps(tool_function)
    def wrapper(*args: Any, **kwargs: Any):
        with redirect_stdout(sys.stderr):
            return tool_function(*args, **kwargs)

    wrapper.__signature__ = signature
    return wrapper


for tool_function in TOOL_FUNCTIONS:
    mcp.tool()(_stdio_safe_tool(tool_function))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
