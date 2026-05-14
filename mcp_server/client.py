from __future__ import annotations

import json
import os
import sys
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolClient(Protocol):
    @property
    def tool_names(self) -> set[str]: ...

    @property
    def tool_schemas(self) -> list[dict[str, Any]]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


class StdioMCPToolClient(AbstractAsyncContextManager["StdioMCPToolClient"]):
    """Local stdio MCP client for Echo workflow tools."""

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command or sys.executable
        self.args = args or ["-m", "mcp_server"]
        self.cwd = cwd
        self.env = env
        self._stdio_context: Any = None
        self._session_context: ClientSession | None = None
        self._session: ClientSession | None = None
        self._tools: list[ToolSpec] = []

    @property
    def tool_names(self) -> set[str]:
        return {tool.name for tool in self._tools}

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            }
            for tool in self._tools
        ]

    async def __aenter__(self) -> "StdioMCPToolClient":
        parameters = StdioServerParameters(
            command=self.command,
            args=self.args,
            cwd=self.cwd,
            env=self.env if self.env is not None else dict(os.environ),
        )
        self._stdio_context = stdio_client(parameters)
        read_stream, write_stream = await self._stdio_context.__aenter__()
        self._session_context = ClientSession(read_stream, write_stream)
        self._session = await self._session_context.__aenter__()
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = [
            ToolSpec(
                name=str(tool.name),
                description=str(tool.description or ""),
                input_schema=dict(tool.inputSchema or {"type": "object", "properties": {}}),
            )
            for tool in result.tools
        ]
        return self

    async def __aexit__(self, exc_type, exc, tb):
        cleanup_error: BaseException | None = None
        if self._session_context is not None:
            try:
                await self._session_context.__aexit__(exc_type, exc, tb)
            except BaseException as session_exc:
                cleanup_error = session_exc
        if self._stdio_context is not None:
            try:
                await self._stdio_context.__aexit__(exc_type, exc, tb)
            except BaseException as stdio_exc:
                cleanup_error = stdio_exc if cleanup_error is None else cleanup_error
        if cleanup_error is not None and exc_type is None:
            raise cleanup_error
        return False

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("MCP tool client is not connected.")
        result = await self._session.call_tool(name, args)
        payload = _call_result_payload(name, result)
        return payload


def local_mcp_tool_client() -> StdioMCPToolClient:
    return StdioMCPToolClient()


def tool_schemas_from_specs(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


def _call_result_payload(name: str, result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        return _error_payload(name, _content_text(result))

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        wrapped_result = structured.get("result")
        if set(structured) == {"result"} and isinstance(wrapped_result, dict):
            return wrapped_result
        return structured

    text = _content_text(result)
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"type": "context", "skill_name": name, "items": [{"content": text}]}
        if isinstance(parsed, dict):
            return parsed
        return {"type": "context", "skill_name": name, "items": [{"content": str(parsed)}]}

    return {"type": "context", "skill_name": name, "items": []}


def _content_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _error_payload(name: str, text: str) -> dict[str, Any]:
    return {
        "type": "context",
        "skill_name": name,
        "items": [],
        "error": text or f"MCP tool '{name}' failed.",
    }
