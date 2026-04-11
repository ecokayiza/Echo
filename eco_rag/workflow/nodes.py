from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from ..chat.chat_model import BaseChatModel, Response
from .prompts import tool_back_message
from .state import WorkflowState, WorkflowStep

SECTION_PATTERN = re.compile(r"(?ms)^\[([a-z_]+)\]\s*(.*?)(?=^\[[a-z_]+\]\s*|\Z)")


@dataclass(frozen=True)
class WorkflowDependencies:
    """Bind runtime dependencies to one workflow instance."""

    model: BaseChatModel
    retrieve_tools: tuple[BaseTool, ...] = ()
    max_retrieve_rounds: int = 2


async def plan_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Choose whether to answer now or enter retrieval."""
    response = await deps.model.generate_response(_workflow_messages(state))
    decision = _decision_from_response(
        response,
        node=WorkflowStep.PLAN.value,
        allow_retrieve=bool(deps.retrieve_tools),
        allowed_tool_names={tool.name for tool in deps.retrieve_tools},
        requested_skill=state.get("requested_skill"),
    )
    content = (response.content or "").strip()
    _emit_record(
        {
            "role": "assistant",
            "content": content,
            "message_type": WorkflowStep.PLAN.value,
            "workflow_turn_id": state["workflow_turn_id"],
            "token_usage": response.token_usage,
        }
    )
    return {
        **state,
        "next_step": decision["next_step"],
        "pending_retrieve": decision.get("pending_retrieve"),
        "prepared_answer": decision.get("answer", ""),
        "workflow_memory": _append_memory(state["workflow_memory"], {"role": "assistant", "content": content}),
    }


async def retrieve_node(state: WorkflowState) -> WorkflowState:
    """Validate the pending retrieval command before tool execution."""
    pending_retrieve = state.get("pending_retrieve")
    if not isinstance(pending_retrieve, dict):
        raise ValueError("Retrieve node requires a pending retrieval command.")
    return {
        **state,
        "next_step": WorkflowStep.TOOL.value,
    }


async def tool_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Execute one pending retrieval command and store the normalized result."""
    pending_retrieve = state.get("pending_retrieve")
    if not isinstance(pending_retrieve, dict):
        raise ValueError("Tool node requires a pending retrieval command.")

    tool_name = str(pending_retrieve.get("name") or "").strip()
    tool_args = dict(pending_retrieve.get("args") or {})
    result = await _run_tool(deps.retrieve_tools, tool_name, tool_args)
    tool_content = _format_tool_message(tool_name, tool_args, result)

    _emit_record(
        {
            "role": "tool",
            "content": tool_content,
            "message_type": WorkflowStep.TOOL.value,
            "workflow_turn_id": state["workflow_turn_id"],
            "tool_name": tool_name,
        }
    )

    next_round = state["retrieve_round"] + 1
    return {
        **state,
        "next_step": WorkflowStep.THINK.value,
        "retrieve_round": next_round,
        "pending_retrieve": None,
        "workflow_memory": _append_memory(
            state["workflow_memory"],
            # Use provider-safe flat transcript roles while keeping the raw tool payload intact.
            {"role": "user", "content": tool_content},
            tool_back_message(
                allow_retrieve=bool(deps.retrieve_tools) and next_round < deps.max_retrieve_rounds,
                available_tools=[tool.name for tool in deps.retrieve_tools],
            ),
        ),
    }


async def think_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Reflect on the accumulated transcript and decide whether to retrieve or answer."""
    allow_retrieve = bool(deps.retrieve_tools) and state["retrieve_round"] < deps.max_retrieve_rounds
    response = await deps.model.generate_response(_workflow_messages(state))
    decision = _decision_from_response(
        response,
        node=WorkflowStep.THINK.value,
        allow_retrieve=allow_retrieve,
        allowed_tool_names={tool.name for tool in deps.retrieve_tools},
    )
    content = (response.content or "").strip()
    _emit_record(
        {
            "role": "assistant",
            "content": content,
            "message_type": WorkflowStep.THINK.value,
            "workflow_turn_id": state["workflow_turn_id"],
            "token_usage": response.token_usage,
        }
    )
    return {
        **state,
        "next_step": decision["next_step"],
        "pending_retrieve": decision.get("pending_retrieve"),
        "prepared_answer": decision.get("answer", ""),
        "workflow_memory": _append_memory(state["workflow_memory"], {"role": "assistant", "content": content}),
    }


async def answer_node(state: WorkflowState) -> WorkflowState:
    """Emit the prepared answer without another model call."""
    answer = _required_block(state.get("prepared_answer"), "answer")
    writer = get_stream_writer()
    writer({"event": "chunk", "data": {"delta": answer, "content": answer}})
    return {
        **state,
        "next_step": None,
        "prepared_answer": answer,
    }


def route_from_state(state: WorkflowState) -> str:
    """Start or resume the workflow from the saved next step."""
    return _next_step(
        state,
        {
            WorkflowStep.PLAN.value,
            WorkflowStep.RETRIEVE.value,
            WorkflowStep.TOOL.value,
            WorkflowStep.THINK.value,
            WorkflowStep.ANSWER.value,
        },
    )


def route_after_plan(state: WorkflowState) -> str:
    """Read the next node after plan."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.ANSWER.value})


def route_after_retrieve(_state: WorkflowState) -> str:
    """Retrieve always transitions into tool execution."""
    return WorkflowStep.TOOL.value


def route_after_tool(_state: WorkflowState) -> str:
    """Tool execution always transitions into think."""
    return WorkflowStep.THINK.value


def route_after_think(state: WorkflowState) -> str:
    """Read the next node after think."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.ANSWER.value})


def _workflow_messages(state: WorkflowState) -> list[dict[str, str]]:
    """Build the provider payload from the flat workflow transcript."""
    return [{"role": item["role"], "content": item["content"]} for item in state["workflow_memory"]]


def _append_memory(
    workflow_memory: list[dict[str, str]],
    *items: dict[str, str],
) -> list[dict[str, str]]:
    """Append new flat-memory items while keeping only role/content pairs."""
    next_memory = [{"role": item["role"], "content": item["content"]} for item in workflow_memory]
    for item in items:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        next_memory.append({"role": role, "content": content})
    return next_memory


def _decision_from_response(
    response: Response,
    *,
    node: str,
    allow_retrieve: bool,
    allowed_tool_names: set[str],
    requested_skill: str | None = None,
) -> dict[str, Any]:
    """Parse one decision-node response."""
    if response.tool_calls:
        raise ValueError(f"{node.title()} node must not use provider-native tool calls.")

    sections = _sections(response.content)
    _required_text(sections.get(node), node)
    next_step = _required_text(sections.get("next"), "next").lower()

    if requested_skill:
        return {
            "next_step": WorkflowStep.RETRIEVE.value,
            "pending_retrieve": {"name": "load_skill", "args": {"skill_name": requested_skill}},
        }

    if next_step == WorkflowStep.ANSWER.value:
        return {
            "next_step": WorkflowStep.ANSWER.value,
            "answer": _required_block(sections.get("answer"), "answer"),
        }

    if next_step != WorkflowStep.RETRIEVE.value:
        raise ValueError(f"{node.title()} node returned invalid next step '{next_step}'.")
    if not allow_retrieve:
        raise ValueError(f"{node.title()} node cannot request more retrieval.")

    return {
        "next_step": WorkflowStep.RETRIEVE.value,
        "pending_retrieve": _parse_retrieve_call(
            _required_block(sections.get("retrieve"), "retrieve"),
            allowed_tool_names,
        ),
    }


async def _run_tool(
    tools: tuple[BaseTool, ...],
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    """Execute one workflow tool and normalize exceptions into a stable payload."""
    tool = next((item for item in tools if item.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Workflow tool '{tool_name}' is not configured.")
    try:
        result = await tool.ainvoke(tool_args)
    except Exception as exc:
        result = {
            "type": "context",
            "skill_name": tool_name,
            "items": [],
            "error": str(exc),
        }
    if isinstance(result, dict):
        return result
    return {"type": "context", "skill_name": tool_name, "items": [{"content": str(result)}]}


def _parse_retrieve_call(text: str, allowed_tool_names: set[str]) -> dict[str, Any]:
    """Parse one safe retrieval command from the bracketed retrieve block."""
    try:
        expression = ast.parse(_strip_code_fences(text).strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid retrieve command: {text}") from exc

    call = expression.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        raise ValueError("Retrieve command must be a simple function call.")
    tool_name = call.func.id.strip()
    if tool_name not in allowed_tool_names:
        allowed = ", ".join(sorted(allowed_tool_names))
        raise ValueError(f"Unknown retrieve tool '{tool_name}'. Allowed tools: {allowed}.")

    args = [_literal_value(node) for node in call.args]
    kwargs = {item.arg: _literal_value(item.value) for item in call.keywords if item.arg}

    if tool_name == "load_skill":
        skill_name = kwargs.get("skill_name", args[0] if args else None)
        if not isinstance(skill_name, str) or not skill_name.strip():
            raise ValueError("load_skill requires one non-empty skill name.")
        return {"name": tool_name, "args": {"skill_name": skill_name.strip()}}

    if tool_name in {"database_search", "legacy_search"}:
        query = kwargs.get("query", args[0] if args else None)
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{tool_name} requires one non-empty query string.")
        payload = {"query": query.strip()}
        if tool_name == "database_search":
            top_k = kwargs.get("top_k")
            if isinstance(top_k, int) and not isinstance(top_k, bool):
                payload["top_k"] = top_k
        return {"name": tool_name, "args": payload}

    if tool_name == "web_search":
        queries = kwargs.get("queries")
        if queries is None:
            if "query" in kwargs:
                queries = [kwargs["query"]]
            elif args:
                queries = args
        if not isinstance(queries, list) or not queries:
            raise ValueError("web_search requires one or more query strings.")
        cleaned = [item.strip() for item in queries if isinstance(item, str) and item.strip()]
        if not cleaned:
            raise ValueError("web_search requires one or more query strings.")
        payload: dict[str, Any] = {"query": cleaned[0]} if len(cleaned) == 1 else {"queries": cleaned}
        max_results = kwargs.get("max_results")
        if isinstance(max_results, int) and not isinstance(max_results, bool):
            payload["max_results"] = max_results
        return {"name": tool_name, "args": payload}

    raise ValueError(f"Retrieve tool '{tool_name}' is not supported by the parser.")


def _literal_value(node: ast.AST) -> Any:
    """Read a restricted literal subset from one AST node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal_value(item) for item in node.elts]
    raise ValueError("Retrieve commands may only use simple literal arguments.")


def _format_tool_message(tool_name: str, tool_args: dict[str, Any], result: dict[str, Any]) -> str:
    """Render one readable tool message for persisted history."""
    heading = f"[tool]\n{tool_name}({', '.join(f'{key}={value!r}' for key, value in tool_args.items())})"
    error = _optional_text(result.get("error"))
    if error:
        return f"{heading}\n\nError: {error}"

    if result.get("type") == "skill":
        content = str(result.get("content") or "").strip()
        skill_name = _optional_text(result.get("skill_name")) or tool_name
        return f"{heading}\n\nLoaded skill: {skill_name}\n\n{content}"

    items = result.get("items")
    if not isinstance(items, list) or not items:
        return f"{heading}\n\nNo results."

    parts = []
    for index, item in enumerate(items, start=1):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            item = {"content": str(item)}
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", item.get("document", "")) or "").strip()
        line = f"{index}. {title}" if title else f"{index}."
        if item.get("url"):
            line = f"{line}\nURL: {item['url']}"
        if content:
            line = f"{line}\n{content}"
        parts.append(line.strip())
    return f"{heading}\n\n" + "\n\n".join(parts)


def _emit_record(record: dict[str, Any]):
    """Emit one buffered persisted record into the LangGraph custom stream."""
    writer = get_stream_writer()
    writer({"event": "record", "data": record})


def _next_step(state: WorkflowState, allowed: set[str]) -> str:
    """Read and validate the next step from state."""
    next_step = state.get("next_step")
    if next_step not in allowed:
        joined = ", ".join(sorted(allowed))
        raise ValueError(f"Workflow next step '{next_step}' is invalid. Allowed: {joined}.")
    return str(next_step)


def _sections(content: str | None) -> dict[str, str]:
    """Parse bracketed sections like [plan] or [answer]."""
    text = _strip_code_fences(content)
    return {
        match.group(1).strip().lower(): match.group(2).strip()
        for match in SECTION_PATTERN.finditer(text)
    }


def _strip_code_fences(content: str | None) -> str:
    """Remove one outer markdown code fence when present."""
    text = (content or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def _required_text(value: Any, label: str) -> str:
    """Read one required string-like value."""
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError(f"Workflow node is missing '{label}'.")
    return text


def _required_block(value: Any, label: str) -> str:
    """Read one required multi-line text block without flattening it."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Workflow node is missing '{label}'.")
    return text


def _optional_text(value: Any) -> str | None:
    """Normalize optional string-like values."""
    text = " ".join(str(value or "").split())
    return text or None
