from __future__ import annotations

import asyncio
import ast
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from ..chat.chat_model import BaseChatModel, Response
from ..skills import list_default_skills
from ..workflow_sections import parse_workflow_sections, render_workflow_section
from .state import WorkflowState, WorkflowStep

ANSWER_CHUNK_PATTERN = re.compile(r"\S+\s*|\s+")
MALFORMED_CLOSING_TAG_PATTERN = re.compile(r"\s*</[^>\r\n]+>\s*$")


@dataclass(frozen=True)
class WorkflowDependencies:
    """Bind runtime dependencies to one workflow instance."""

    model: BaseChatModel
    retrieve_tools: tuple[BaseTool, ...] = ()
    max_retrieve_rounds: int = 2


async def plan_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Choose whether to answer now or enter retrieval."""
    response, streamed_answer = await _stream_decision_response(
        state,
        deps,
        node=WorkflowStep.PLAN.value,
    )
    decision = _decision_from_response(
        response,
        node=WorkflowStep.PLAN.value,
        allow_retrieve=bool(deps.retrieve_tools),
        allowed_tool_names={tool.name for tool in deps.retrieve_tools},
        requested_skill=state.get("requested_skill"),
    )
    content = (response.content or "").strip()
    pending_retrieve = _pending_retrieve_with_native_tool_call(state, decision.get("pending_retrieve"))
    return {
        **state,
        "next_step": decision["next_step"],
        "pending_retrieve": pending_retrieve,
        "prepared_answer": decision.get("answer", ""),
        "streamed_answer": streamed_answer if decision["next_step"] == WorkflowStep.ANSWER.value else "",
        "workflow_memory": _append_memory(
            state["workflow_memory"],
            _assistant_memory_item(content, pending_retrieve),
        ),
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
            "id": _record_id(state, WorkflowStep.TOOL.value, suffix=str(state["retrieve_round"] + 1)),
            "role": "tool",
            "content": tool_content,
            "message_type": WorkflowStep.TOOL.value,
            "workflow_turn_id": state["workflow_turn_id"],
            "tool_name": tool_name,
            "tool_call_id": _optional_text(pending_retrieve.get("tool_call_id")),
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
            {
                "role": "tool",
                "content": tool_content,
                "tool_call_id": _optional_text(pending_retrieve.get("tool_call_id")),
            },
        ),
    }


async def think_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Reflect on the accumulated transcript and decide whether to retrieve or answer."""
    allow_retrieve = bool(deps.retrieve_tools) and state["retrieve_round"] < deps.max_retrieve_rounds
    response, streamed_answer = await _stream_decision_response(
        state,
        deps,
        node=WorkflowStep.THINK.value,
    )
    decision = _decision_from_response(
        response,
        node=WorkflowStep.THINK.value,
        allow_retrieve=allow_retrieve,
        allowed_tool_names={tool.name for tool in deps.retrieve_tools},
    )
    content = (response.content or "").strip()
    pending_retrieve = _pending_retrieve_with_native_tool_call(state, decision.get("pending_retrieve"))
    return {
        **state,
        "next_step": decision["next_step"],
        "pending_retrieve": pending_retrieve,
        "prepared_answer": decision.get("answer", ""),
        "streamed_answer": streamed_answer if decision["next_step"] == WorkflowStep.ANSWER.value else "",
        "workflow_memory": _append_memory(
            state["workflow_memory"],
            _assistant_memory_item(content, pending_retrieve),
        ),
    }


async def answer_node(state: WorkflowState) -> WorkflowState:
    """Emit the prepared answer without another model call."""
    answer = _required_block(state.get("prepared_answer"), "answer")
    already_streamed = str(state.get("streamed_answer") or "")
    remaining = answer[len(already_streamed) :] if answer.startswith(already_streamed) else answer
    writer = get_stream_writer()
    chunks = _answer_chunks(remaining)
    streamed = ""
    for index, chunk in enumerate(chunks):
        streamed = f"{streamed}{chunk}"
        writer(
            {
                "event": "chunk",
                "data": {
                    "delta": chunk,
                    "content": f"{already_streamed}{streamed}",
                },
            }
        )
        if index < len(chunks) - 1:
            await asyncio.sleep(0)
    return {
        **state,
        "next_step": None,
        "prepared_answer": answer,
        "streamed_answer": answer,
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


def _workflow_messages(state: WorkflowState) -> list[dict[str, Any]]:
    """Build the provider payload from the flat workflow transcript."""
    payloads: list[dict[str, Any]] = []
    for item in state["workflow_memory"]:
        payload: dict[str, Any] = {"role": item["role"], "content": item["content"]}
        tool_calls = item.get("tool_calls")
        if item["role"] == "assistant" and isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = [dict(entry) for entry in tool_calls if isinstance(entry, dict)]
        tool_call_id = _optional_text(item.get("tool_call_id"))
        if item["role"] == "tool" and tool_call_id:
            payload["tool_call_id"] = tool_call_id
        payloads.append(payload)
    return payloads


def _append_memory(
    workflow_memory: list[dict[str, Any]],
    *items: dict[str, Any],
) -> list[dict[str, Any]]:
    """Append new flat-memory items while keeping only role/content pairs."""
    next_memory: list[dict[str, Any]] = []
    for item in workflow_memory:
        payload: dict[str, Any] = {"role": item["role"], "content": item["content"]}
        tool_calls = item.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = [dict(entry) for entry in tool_calls if isinstance(entry, dict)]
        tool_call_id = _optional_text(item.get("tool_call_id"))
        if tool_call_id:
            payload["tool_call_id"] = tool_call_id
        next_memory.append(payload)
    for item in items:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "user", "assistant", "tool"} or not content:
            continue
        payload = {"role": role, "content": content}
        tool_calls = item.get("tool_calls")
        if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = [dict(entry) for entry in tool_calls if isinstance(entry, dict)]
        tool_call_id = _optional_text(item.get("tool_call_id"))
        if role == "tool" and tool_call_id:
            payload["tool_call_id"] = tool_call_id
        next_memory.append(payload)
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
    try:
        if response.tool_calls:
            raise ValueError(f"{node.title()} node must not use provider-native tool calls.")

        content = (response.content or "").strip()
        sections = _sections(content, allow_unclosed=True)

        if requested_skill:
            return {
                "next_step": WorkflowStep.RETRIEVE.value,
                "pending_retrieve": {"name": "load_skill", "args": {"skill_name": requested_skill}},
            }

        if not sections:
            return {
                "next_step": WorkflowStep.ANSWER.value,
                "answer": _required_block(content, "answer"),
            }

        fallback_answer = _fallback_answer_from_node_only_response(sections, node=node)
        if fallback_answer is not None:
            return {
                "next_step": WorkflowStep.ANSWER.value,
                "answer": fallback_answer,
            }

        next_step = _decision_action(sections, node=node)

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
    except ValueError as exc:
        raise ValueError(_with_llm_raw_output(str(exc), response.content)) from exc


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
    """Parse one safe retrieval command from the retrieve block."""
    cleaned_text = _clean_retrieve_command(text)
    try:
        expression = ast.parse(cleaned_text, mode="eval")
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
        if _is_default_skill(skill_name):
            raise ValueError(f"Default skill '{skill_name.strip()}' is already loaded and must not be loaded again.")
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

    if tool_name == "web_fetch":
        url = kwargs.get("url", args[0] if args else None)
        if not isinstance(url, str) or not url.strip():
            raise ValueError("web_fetch requires one non-empty URL.")
        parsed_url = urlparse(url.strip())
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("web_fetch requires an http or https URL.")
        payload = {"url": url.strip()}
        max_chars = kwargs.get("max_chars")
        if isinstance(max_chars, int) and not isinstance(max_chars, bool):
            payload["max_chars"] = max_chars
        return {"name": tool_name, "args": payload}

    if tool_name == "workspace_list_files":
        path = kwargs.get("path", args[0] if args else ".")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("workspace_list_files requires a non-empty path string.")
        payload: dict[str, Any] = {"path": path.strip()}
        recursive = kwargs.get("recursive")
        if isinstance(recursive, bool):
            payload["recursive"] = recursive
        max_results = kwargs.get("max_results")
        if isinstance(max_results, int) and not isinstance(max_results, bool):
            payload["max_results"] = max_results
        return {"name": tool_name, "args": payload}

    if tool_name == "workspace_read_file":
        file_path = kwargs.get("file_path", kwargs.get("path", args[0] if args else None))
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("workspace_read_file requires one non-empty file_path string.")
        payload = {"file_path": file_path.strip()}
        max_chars = kwargs.get("max_chars")
        if isinstance(max_chars, int) and not isinstance(max_chars, bool):
            payload["max_chars"] = max_chars
        return {"name": tool_name, "args": payload}

    if tool_name == "workspace_write_file":
        file_path = kwargs.get("file_path", kwargs.get("path", args[0] if args else None))
        content = kwargs.get("content", args[1] if len(args) > 1 else None)
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("workspace_write_file requires one non-empty file_path string.")
        if not isinstance(content, str):
            raise ValueError("workspace_write_file requires content as a string.")
        payload = {"file_path": file_path.strip(), "content": content}
        overwrite = kwargs.get("overwrite")
        if isinstance(overwrite, bool):
            payload["overwrite"] = overwrite
        return {"name": tool_name, "args": payload}

    if tool_name == "workspace_edit_file":
        file_path = kwargs.get("file_path", kwargs.get("path", args[0] if args else None))
        old_text = kwargs.get("old_text", args[1] if len(args) > 1 else None)
        new_text = kwargs.get("new_text", args[2] if len(args) > 2 else None)
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("workspace_edit_file requires one non-empty file_path string.")
        if not isinstance(old_text, str):
            raise ValueError("workspace_edit_file requires old_text as a string.")
        if not isinstance(new_text, str):
            raise ValueError("workspace_edit_file requires new_text as a string.")
        payload = {"file_path": file_path.strip(), "old_text": old_text, "new_text": new_text}
        expected_replacements = kwargs.get("expected_replacements")
        if isinstance(expected_replacements, int) and not isinstance(expected_replacements, bool):
            payload["expected_replacements"] = expected_replacements
        return {"name": tool_name, "args": payload}

    raise ValueError(f"Retrieve tool '{tool_name}' is not supported by the parser.")


def _clean_retrieve_command(text: str) -> str:
    """Remove malformed provider closing tags from one retrieve command."""
    lines = []
    for line in str(text or "").strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("</") and stripped.endswith(">"):
            continue
        lines.append(line)
    return MALFORMED_CLOSING_TAG_PATTERN.sub("", "\n".join(lines).strip()).strip()


def _is_default_skill(skill_name: str) -> bool:
    requested = skill_name.strip().lower().replace("_", "-")
    defaults = {skill.lower().replace("_", "-") for skill in list_default_skills()}
    return requested in defaults


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
    heading = f"{tool_name}({', '.join(f'{key}={value!r}' for key, value in tool_args.items())})"
    error = _optional_text(result.get("error"))
    if error:
        return render_workflow_section("tool", f"{heading}\n\nError: {error}")

    if result.get("type") == "skill":
        content = str(result.get("content") or "").strip()
        skill_name = _optional_text(result.get("skill_name")) or tool_name
        return render_workflow_section("tool", f"{heading}\n\nLoaded skill: {skill_name}\n\n{content}")

    items = result.get("items")
    if not isinstance(items, list) or not items:
        return render_workflow_section("tool", f"{heading}\n\nNo results.")

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
    return render_workflow_section("tool", f"{heading}\n\n" + "\n\n".join(parts))


def _emit_record(record: dict[str, Any]):
    """Emit one buffered persisted record into the LangGraph custom stream."""
    writer = get_stream_writer()
    writer({"event": "record", "data": record})


async def _stream_decision_response(
    state: WorkflowState,
    deps: WorkflowDependencies,
    *,
    node: str,
) -> tuple[Response, str]:
    """Stream one plan/think decision, emitting live record updates and answer chunks."""
    usage: dict[str, Any] = {}
    content = ""
    streamed_answer = ""
    record_id = _record_id(state, node)
    writer = get_stream_writer()

    def on_usage(payload: dict[str, Any] | None):
        if isinstance(payload, dict):
            usage.clear()
            usage.update(payload)

    async for chunk in deps.model.stream_response(
        _workflow_messages(state),
        callbacks={"on_usage": on_usage},
    ):
        if not chunk:
            continue
        content = f"{content}{chunk}"
        stripped = content.strip()
        if stripped:
            _emit_record(
                {
                    "id": record_id,
                    "role": "assistant",
                    "content": stripped,
                    "message_type": node,
                    "workflow_turn_id": state["workflow_turn_id"],
                    "persist": False,
                }
            )
            streamed_answer = _emit_streaming_answer(
                writer,
                sections=_sections(stripped, allow_unclosed=True),
                streamed_answer=streamed_answer,
            )

    final_content = content.strip()
    if not final_content:
        raise ValueError(f"{node.title()} node returned an empty response.")

    _emit_record(
        {
            "id": record_id,
            "role": "assistant",
            "content": final_content,
            "message_type": node,
            "workflow_turn_id": state["workflow_turn_id"],
            "token_usage": usage or None,
            "persist": True,
        }
    )
    streamed_answer = _emit_streaming_answer(
        writer,
        sections=_sections(final_content),
        streamed_answer=streamed_answer,
    )
    return (
        Response(
            content=final_content,
            tool_calls=None,
            token_usage=usage or None,
            raw_response=None,
        ),
        streamed_answer,
    )


def _emit_streaming_answer(
    writer,
    *,
    sections: dict[str, str],
    streamed_answer: str,
) -> str:
    """Emit live answer chunks once the response has entered the answer block."""
    answer = str(sections.get("answer") or "")
    if not answer or _has_action_block(sections, "retrieve"):
        return streamed_answer

    if answer.startswith(streamed_answer):
        delta = answer[len(streamed_answer) :]
    else:
        delta = answer
    if not delta:
        return streamed_answer

    writer({"event": "chunk", "data": {"delta": delta, "content": answer}})
    return answer


def _next_step(state: WorkflowState, allowed: set[str]) -> str:
    """Read and validate the next step from state."""
    next_step = state.get("next_step")
    if next_step not in allowed:
        joined = ", ".join(sorted(allowed))
        raise ValueError(f"Workflow next step '{next_step}' is invalid. Allowed: {joined}.")
    return str(next_step)


def _sections(content: str | None, *, allow_unclosed: bool = False) -> dict[str, str]:
    """Parse workflow sections, preferring paired XML-style tags."""
    return parse_workflow_sections(content, allow_unclosed=allow_unclosed)


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


def _with_llm_raw_output(detail: str, content: str | None, *, limit: int = 2000) -> str:
    """Append one bounded raw-model output block to workflow decision errors."""
    raw = (content or "").strip()
    if not raw:
        rendered = "<empty>"
    elif len(raw) > limit:
        rendered = f"{raw[:limit]}\n...(truncated {len(raw) - limit} chars)"
    else:
        rendered = raw
    return f"{detail}\nLLM raw output:\n{rendered}"


def _decision_action(sections: dict[str, str], *, node: str) -> str:
    """Resolve one decision-node route from its action blocks."""
    has_retrieve = _has_action_block(sections, "retrieve")
    has_answer = _has_action_block(sections, "answer")
    if has_retrieve and not has_answer:
        return WorkflowStep.RETRIEVE.value
    if has_answer and not has_retrieve:
        return WorkflowStep.ANSWER.value
    raise ValueError(
        f"{node.title()} node must include exactly one of <retrieve> or <answer>."
    )


def _fallback_answer_from_node_only_response(sections: dict[str, str], *, node: str) -> str | None:
    """Treat a completed think-only response as an answer instead of failing the turn."""
    if node != WorkflowStep.THINK.value:
        return None
    if _has_action_block(sections, "retrieve") or _has_action_block(sections, "answer"):
        return None
    answer = _required_block(sections.get(node), "answer")
    return answer


def _has_action_block(sections: dict[str, str], name: str) -> bool:
    """Return whether one non-empty action block exists."""
    return bool(_optional_text(sections.get(name)))


def _record_id(state: WorkflowState, node: str, *, suffix: str | None = None) -> str:
    """Build one stable live-record id for the current workflow turn."""
    parts = [state["workflow_turn_id"], node]
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def _tool_call_id(state: WorkflowState, *, round_number: int) -> str:
    """Build one stable provider-native tool call id for a retrieval round."""
    return f"{state['workflow_turn_id']}:tool_call:{round_number}"


def _pending_retrieve_with_native_tool_call(
    state: WorkflowState,
    pending_retrieve: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Attach a stable tool_call_id to one pending retrieval command."""
    if not isinstance(pending_retrieve, dict):
        return None
    payload = {
        "name": str(pending_retrieve.get("name") or "").strip(),
        "args": dict(pending_retrieve.get("args") or {}),
    }
    if not payload["name"]:
        return None
    payload["tool_call_id"] = _optional_text(pending_retrieve.get("tool_call_id")) or _tool_call_id(
        state,
        round_number=state["retrieve_round"] + 1,
    )
    return payload


def _assistant_memory_item(content: str, pending_retrieve: dict[str, Any] | None) -> dict[str, Any]:
    """Build one assistant transcript item, synthesizing native tool_calls when retrieval is pending."""
    payload: dict[str, Any] = {"role": "assistant", "content": content}
    if not isinstance(pending_retrieve, dict):
        return payload
    tool_call_id = _optional_text(pending_retrieve.get("tool_call_id"))
    tool_name = str(pending_retrieve.get("name") or "").strip()
    tool_args = pending_retrieve.get("args")
    if not tool_call_id or not tool_name or not isinstance(tool_args, dict):
        return payload
    payload["tool_calls"] = [
        {
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(tool_args, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            },
        }
    ]
    return payload


def _answer_chunks(answer: str, target_size: int = 48) -> list[str]:
    """Split one prepared answer into readable stream chunks."""
    text = answer.strip()
    if not text or len(text) <= target_size:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for piece in ANSWER_CHUNK_PATTERN.findall(text):
        if current and len(current) + len(piece) > target_size:
            chunks.append(current)
            current = piece
            continue
        current = f"{current}{piece}"
    if current:
        chunks.append(current)
    return chunks or [text]
