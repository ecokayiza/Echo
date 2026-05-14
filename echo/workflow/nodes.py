from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from langgraph.config import get_stream_writer

from ..chat.chat_model import BaseChatModel, Response
from mcp_server.client import ToolClient
from ..workflow_sections import (
    parse_workflow_sections,
    render_workflow_section,
    render_workflow_sections,
    workflow_section_entries,
)
from .state import WorkflowState, WorkflowStep

ANSWER_CHUNK_PATTERN = re.compile(r"\S+\s*|\s+")
TEXTUAL_RETRIEVE_PATTERN = re.compile(r"</?\s*(?:echo_)?retrieve\b", re.IGNORECASE)


@dataclass(frozen=True)
class WorkflowDependencies:
    """Bind runtime dependencies to one workflow instance."""

    model: BaseChatModel
    tool_client: ToolClient
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
        allow_retrieve=bool(deps.tool_client.tool_names),
        allowed_tool_names=deps.tool_client.tool_names,
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
    """Validate the pending native tool call before tool execution."""
    pending_retrieve = state.get("pending_retrieve")
    if not isinstance(pending_retrieve, dict):
        raise ValueError("Retrieve node requires a pending native tool call.")
    return {
        **state,
        "next_step": WorkflowStep.TOOL.value,
    }


async def tool_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Execute one pending MCP tool call and store the normalized result."""
    pending_retrieve = state.get("pending_retrieve")
    if not isinstance(pending_retrieve, dict):
        raise ValueError("Tool node requires a pending native tool call.")

    tool_name = str(pending_retrieve.get("name") or "").strip()
    tool_args = dict(pending_retrieve.get("args") or {})
    result = await _run_tool(deps.tool_client, tool_name, tool_args)
    tool_content = _format_tool_message(tool_name, tool_args, result)
    tool_call_id = _optional_text(pending_retrieve.get("tool_call_id"))

    _emit_record(
        {
            "id": _record_id(state, WorkflowStep.TOOL.value, suffix=str(state["retrieve_round"] + 1)),
            "role": "tool",
            "content": tool_content,
            "message_type": WorkflowStep.TOOL.value,
            "workflow_turn_id": state["workflow_turn_id"],
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
        }
    )

    next_round = state["retrieve_round"] + 1
    tool_memory = {
        "role": "tool",
        "content": tool_content,
        "tool_call_id": tool_call_id,
    }
    return {
        **state,
        "next_step": WorkflowStep.THINK.value,
        "retrieve_round": next_round,
        "pending_retrieve": None,
        "workflow_memory": _append_memory(
            state["workflow_memory"],
            tool_memory,
            *_visual_memory_items(tool_name, result),
        ),
    }


async def think_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Reflect on the accumulated transcript and decide whether to retrieve or answer."""
    allow_retrieve = bool(deps.tool_client.tool_names) and state["retrieve_round"] < deps.max_retrieve_rounds
    response, streamed_answer = await _stream_decision_response(
        state,
        deps,
        node=WorkflowStep.THINK.value,
    )
    decision = _decision_from_response(
        response,
        node=WorkflowStep.THINK.value,
        allow_retrieve=allow_retrieve,
        allowed_tool_names=deps.tool_client.tool_names,
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
    """Append new flat-memory items while keeping provider transcript fields."""
    next_memory: list[dict[str, Any]] = []
    for item in [*workflow_memory, *items]:
        role = str(item.get("role") or "").strip()
        content = _message_content(item.get("content"))
        if role not in {"system", "user", "assistant", "tool"} or not content:
            continue
        payload: dict[str, Any] = {"role": role, "content": content}
        tool_calls = item.get("tool_calls")
        if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = [dict(entry) for entry in tool_calls if isinstance(entry, dict)]
        tool_call_id = _optional_text(item.get("tool_call_id"))
        if role == "tool" and tool_call_id:
            payload["tool_call_id"] = tool_call_id
        next_memory.append(payload)
    return next_memory


def _message_content(value: Any) -> Any:
    if isinstance(value, list):
        parts = [dict(item) for item in value if isinstance(item, dict)]
        return parts or None
    text = str(value or "").strip()
    return text or None


def _visual_memory_items(tool_name: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build transient user image messages for vision-capable models."""
    items = result.get("items")
    if tool_name != "web_fetch" or not isinstance(items, list):
        return []

    messages = []
    for item in items:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("image_url") or "").strip()
        if not image_url:
            continue
        title = _optional_text(item.get("title")) or "web_fetch screenshot"
        url = _optional_text(item.get("url"))
        text = f"Screenshot from web_fetch: {title}"
        if url:
            text = f"{text}\nURL: {url}"
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        )
    return messages


def _decision_from_response(
    response: Response,
    *,
    node: str,
    allow_retrieve: bool,
    allowed_tool_names: set[str],
    requested_skill: str | None = None,
) -> dict[str, Any]:
    """Parse one native-tool-only decision-node response."""
    try:
        content = (response.content or "").strip()
        if TEXTUAL_RETRIEVE_PATTERN.search(content):
            raise ValueError("Textual retrieve blocks are not supported. Use a provider-native tool call.")

        sections = _sections(content, allow_unclosed=True)

        if requested_skill:
            if "load_skill" not in allowed_tool_names:
                raise ValueError("The load_skill tool is not configured.")
            return {
                "next_step": WorkflowStep.RETRIEVE.value,
                "pending_retrieve": {"name": "load_skill", "args": {"skill_name": requested_skill}},
            }

        if response.tool_calls:
            if _has_action_block(sections, "answer"):
                raise ValueError(f"{node.title()} node cannot include both <echo_answer> and a native tool call.")
            if not allow_retrieve:
                raise ValueError(f"{node.title()} node cannot request more retrieval.")
            return {
                "next_step": WorkflowStep.RETRIEVE.value,
                "pending_retrieve": _pending_retrieve_from_native_tool_call(response.tool_calls, allowed_tool_names),
            }

        if _has_action_block(sections, "answer"):
            return {
                "next_step": WorkflowStep.ANSWER.value,
                "answer": _required_block(sections.get("answer"), "answer"),
            }

        raise ValueError(f"{node.title()} node must include <echo_answer> or exactly one provider-native tool call.")
    except ValueError as exc:
        raise ValueError(_with_llm_raw_output(str(exc), response.content)) from exc


def _pending_retrieve_from_native_tool_call(
    tool_calls: list[dict[str, Any]],
    allowed_tool_names: set[str],
) -> dict[str, Any]:
    """Convert one provider-native tool call into an Echo pending tool call."""
    calls = [item for item in tool_calls if isinstance(item, dict) and str(item.get("name") or "").strip()]
    if len(calls) != 1:
        raise ValueError("Workflow decisions must include exactly one provider-native tool call.")

    tool_call = calls[0]
    name = str(tool_call.get("name") or "").strip()
    if name not in allowed_tool_names:
        allowed = ", ".join(sorted(allowed_tool_names))
        raise ValueError(f"Unknown tool '{name}'. Allowed tools: {allowed}.")

    args = tool_call.get("args")
    pending: dict[str, Any] = {"name": name, "args": dict(args) if isinstance(args, dict) else {}}
    tool_call_id = _optional_text(tool_call.get("id"))
    if tool_call_id:
        pending["tool_call_id"] = tool_call_id
    return pending


async def _run_tool(
    tool_client: ToolClient,
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    """Execute one workflow MCP tool and normalize exceptions into a stable payload."""
    if tool_name not in tool_client.tool_names:
        raise ValueError(f"Workflow tool '{tool_name}' is not configured.")
    try:
        result = await tool_client.call_tool(tool_name, tool_args)
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
        if item.get("image_url"):
            line = f"{line}\nScreenshot: attached for vision model."
        fetch_error = _optional_text(item.get("fetch_error"))
        if fetch_error:
            line = f"{line}\nHTML fetch failed: {fetch_error}"
        screenshot_error = _optional_text(item.get("screenshot_error"))
        if screenshot_error:
            line = f"{line}\nScreenshot unavailable: {screenshot_error}"
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
    native_tool_calls: list[dict[str, Any]] = []
    content = ""
    streamed_answer = ""
    record_id = _record_id(state, node)
    writer = get_stream_writer()

    def on_usage(payload: dict[str, Any] | None):
        if isinstance(payload, dict):
            usage.clear()
            usage.update(payload)

    def on_tool_calls(payload: list[dict[str, Any]] | None):
        if isinstance(payload, list):
            native_tool_calls.clear()
            native_tool_calls.extend(dict(item) for item in payload if isinstance(item, dict))

    async for chunk in deps.model.stream_response(
        _workflow_messages(state),
        tools=deps.tool_client.tool_schemas,
        callbacks={"on_usage": on_usage, "on_tool_calls": on_tool_calls},
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

    final_content = _sanitize_decision_content(
        _with_native_tool_call_content(node, content.strip(), native_tool_calls)
    )
    if not final_content:
        raise ValueError(f"{node.title()} node returned an empty response.")

    record = {
        "id": record_id,
        "role": "assistant",
        "content": final_content,
        "message_type": _record_message_type(node, final_content, native_tool_calls),
        "workflow_turn_id": state["workflow_turn_id"],
        "token_usage": usage or None,
        "persist": True,
    }
    provider_tool_calls = _provider_tool_calls(native_tool_calls)
    if provider_tool_calls:
        record["tool_calls"] = provider_tool_calls
    _emit_record(record)

    streamed_answer = _emit_streaming_answer(
        writer,
        sections=_sections(final_content),
        streamed_answer=streamed_answer,
    )
    return (
        Response(
            content=final_content,
            tool_calls=native_tool_calls or None,
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
    if not answer:
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
    """Parse current Echo workflow sections."""
    return parse_workflow_sections(content, allow_unclosed=allow_unclosed)


def _sanitize_decision_content(content: str) -> str:
    """Keep only current visible workflow sections from one model decision."""
    entries = [
        (name, block)
        for name, block in workflow_section_entries(content, allow_unclosed=True)
        if name in {"plan", "think", "answer"} and block
    ]
    return render_workflow_sections(entries) if entries else content.strip()


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


def _with_native_tool_call_content(node: str, content: str, tool_calls: list[dict[str, Any]]) -> str:
    """Ensure native tool-call decisions still have a visible node record."""
    if not tool_calls:
        return content

    sections = _sections(content, allow_unclosed=True)
    first = next((item for item in tool_calls if isinstance(item, dict) and item.get("name")), None)
    if not first:
        return content

    node_block = _optional_text(sections.get(node))
    if node_block:
        return render_workflow_section(node, node_block)

    return render_workflow_section(node, f"Native tool call: {first['name']}")


def _record_message_type(node: str, content: str, tool_calls: list[dict[str, Any]]) -> str:
    """Classify persisted decision records by the visible action they carry."""
    if tool_calls:
        return node
    if _has_action_block(_sections(content), "answer"):
        return WorkflowStep.ANSWER.value
    return node


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
    """Build one assistant transcript item with native tool_calls when retrieval is pending."""
    payload: dict[str, Any] = {"role": "assistant", "content": content}
    provider_tool_calls = _provider_tool_calls([pending_retrieve] if isinstance(pending_retrieve, dict) else [])
    if provider_tool_calls:
        payload["tool_calls"] = provider_tool_calls
    return payload


def _provider_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    provider_calls = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        tool_call_id = _optional_text(tool_call.get("tool_call_id")) or _optional_text(tool_call.get("id"))
        tool_name = str(tool_call.get("name") or "").strip()
        tool_args = tool_call.get("args")
        if not tool_call_id or not tool_name or not isinstance(tool_args, dict):
            continue
        provider_calls.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_args, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                },
            }
        )
    return provider_calls or None


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
