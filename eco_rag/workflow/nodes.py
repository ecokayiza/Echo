from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.tools import BaseTool

from ..chat.chat_model import BaseChatModel
from ..skills import load_skill_document
from .prompts import answer_messages, plan_messages, retrieve_messages, think_messages
from .state import WorkflowState, WorkflowStep, merge_token_usage

DEFAULT_WORKFLOW_PROMPT = "You are the chat assistant for Eco_RAG."


class RouteDecision(TypedDict):
    """Store one simple workflow route decision."""

    next_step: str
    reason: str


class RetrieveDecision(RouteDecision, total=False):
    """Store the retrieve decision plus an optional tool request."""

    tool_name: str | None
    tool_args: dict[str, Any]


class ThinkDecision(RouteDecision):
    """Store the think-node reflection payload."""

    conclusion: str
    update_plan: str
    self_reflection: str


@dataclass(frozen=True)
class WorkflowDependencies:
    """Bind runtime dependencies to one workflow instance."""

    model: BaseChatModel
    retrieve_tools: tuple[BaseTool, ...] = ()
    skills_prompt: str = ""
    system_prompt: str = DEFAULT_WORKFLOW_PROMPT
    max_retrieve_count: int = 2
    max_skill_loads: int = 1


async def plan_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Choose the first workflow action."""
    payload, usage, output = await _json_response(
        deps.model,
        plan_messages(
            state["query"],
            state["context"],
            bool(deps.retrieve_tools),
            state.get("requested_skill"),
        ),
    )
    decision = _plan_decision(
        payload,
        requested_skill=state.get("requested_skill"),
        retrieval_enabled=bool(deps.retrieve_tools),
    )
    return {
        **state,
        "next_step": decision["next_step"],
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.PLAN.value,
        "last_detail": _route_detail(decision),
        "trace": _append_trace(
            state,
            {
                "node": WorkflowStep.PLAN.value,
                "output": output,
                "decision": dict(decision),
            },
        ),
    }


async def inject_skills_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Inject the skill catalog and any explicit /skill request before retrieval."""
    loaded_skills = list(state["loaded_skills"])
    requested_skill = state.get("requested_skill")
    detail = "Injected skills catalog before retrieval."

    if requested_skill:
        skill_name, content = load_skill_document(requested_skill)
        loaded_skills = _merge_loaded_skills(loaded_skills, [{"name": skill_name, "content": content}])
        detail = f"Injected skills catalog and preloaded requested skill '{skill_name}'."

    return {
        **state,
        "skills_prompt": deps.skills_prompt,
        "loaded_skills": loaded_skills,
        "last_node": WorkflowStep.INJECT_SKILLS.value,
        "last_detail": detail,
    }


async def retrieve_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Let the model choose one tool action, then update retrieval state."""
    if not deps.retrieve_tools:
        raise ValueError("Retrieve node requires at least one tool.")

    payload, usage, output = await _json_response(
        deps.model,
        retrieve_messages(
            state["query"],
            state["context"],
            state["context_items"],
            state["skills_prompt"] or deps.skills_prompt,
            state["loaded_skills"],
            [tool.name for tool in deps.retrieve_tools],
            state.get("requested_skill"),
            state["skill_load_count"] < deps.max_skill_loads,
        ),
    )
    decision = _retrieve_decision(payload, {tool.name for tool in deps.retrieve_tools})
    next_step = decision["next_step"]
    reason = decision["reason"]
    loaded_skills = list(state["loaded_skills"])
    context_items = list(state["context_items"])
    skill_load_count = state["skill_load_count"]
    tool_result: dict[str, Any] | None = None

    if decision.get("tool_name"):
        tool_name = str(decision["tool_name"])
        tool_args = dict(decision.get("tool_args") or {})
        if tool_name == "load_skill" and skill_load_count >= deps.max_skill_loads:
            next_step = WorkflowStep.THINK.value
            reason = f"{reason} Skill loading limit reached, so retrieval will continue without another skill load."
        else:
            tool_result = await _run_tool(deps.retrieve_tools, tool_name, tool_args)
            loaded_skills = _merge_loaded_skills(loaded_skills, _loaded_skills_from_tool(tool_result))
            context_items = _merge_context_items(context_items, _context_items_from_tool(tool_result))
            if tool_name == "load_skill":
                skill_load_count += 1
                next_step = WorkflowStep.RETRIEVE.value
            else:
                next_step = WorkflowStep.THINK.value

    detail = _retrieve_detail(decision, next_step, reason, tool_result)
    retrieve_increment = 0 if next_step == WorkflowStep.RETRIEVE.value else 1
    return {
        **state,
        "loaded_skills": loaded_skills,
        "context_items": context_items,
        "next_step": next_step,
        "retrieve_count": state["retrieve_count"] + retrieve_increment,
        "skill_load_count": skill_load_count,
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.RETRIEVE.value,
        "last_detail": detail,
        "trace": _append_trace(
            state,
            {
                "node": WorkflowStep.RETRIEVE.value,
                "output": output,
                "decision": {
                    **dict(decision),
                    "next_step": next_step,
                    "reason": reason,
                },
                "tool_result": _summarize_tool_result(tool_result),
            },
        ),
    }


async def think_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Reflect on the current evidence and decide whether to retrieve more or answer."""
    allow_retrieve = bool(deps.retrieve_tools) and state["retrieve_count"] < deps.max_retrieve_count
    payload, usage, output = await _json_response(
        deps.model,
        think_messages(
            state["query"],
            state["context"],
            state["context_items"],
            allow_retrieve,
        ),
    )
    decision = _think_decision(payload, allow_retrieve=allow_retrieve)
    return {
        **state,
        "next_step": decision["next_step"],
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.THINK.value,
        "last_detail": _think_detail(decision),
        "trace": _append_trace(
            state,
            {
                "node": WorkflowStep.THINK.value,
                "output": output,
                "decision": dict(decision),
            },
        ),
    }


def answer_node_messages(state: WorkflowState, deps: WorkflowDependencies) -> list[dict[str, str]]:
    """Build the final answer prompt payload."""
    return answer_messages(
        state["query"],
        state["context"],
        state["context_items"],
        deps.system_prompt,
    )


def finalize_answer_state(
    state: WorkflowState,
    content: str,
    token_usage: dict[str, Any] | None,
) -> WorkflowState:
    """Finalize the workflow after the streamed answer is complete."""
    answer = content.strip()
    if not answer:
        raise ValueError("Answer node returned an empty reply.")
    return {
        **state,
        "answer": answer,
        "next_step": None,
        "token_usage": merge_token_usage(state["token_usage"], token_usage),
        "last_node": WorkflowStep.ANSWER.value,
        "last_detail": "Generated final answer.",
        "trace": _append_trace(
            state,
            {
                "node": WorkflowStep.ANSWER.value,
                "output": answer,
            },
        ),
    }


def route_after_plan(state: WorkflowState) -> str:
    """Read the next node after plan."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.ANSWER.value})


def route_after_retrieve(state: WorkflowState) -> str:
    """Read the next node after retrieve."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.THINK.value})


def route_after_think(state: WorkflowState) -> str:
    """Read the next node after think."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.ANSWER.value})


async def _json_response(
    model: BaseChatModel,
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    """Call the model once and parse the first JSON object from its response."""
    response = await model.generate_response(messages)
    output = (response.content or "").strip()
    return _json_object(output), response.token_usage, output


def _plan_decision(
    payload: dict[str, Any],
    *,
    requested_skill: str | None,
    retrieval_enabled: bool,
) -> RouteDecision:
    """Validate the planner decision."""
    allowed = {WorkflowStep.ANSWER.value}
    if retrieval_enabled:
        allowed.add(WorkflowStep.RETRIEVE.value)
    decision = _route_decision(payload, allowed)
    if requested_skill:
        decision["next_step"] = WorkflowStep.RETRIEVE.value
    return decision


def _retrieve_decision(payload: dict[str, Any], tool_names: set[str]) -> RetrieveDecision:
    """Validate one retrieve-node tool decision."""
    decision: RetrieveDecision = {
        **_route_decision(payload, {WorkflowStep.RETRIEVE.value, WorkflowStep.THINK.value}),
        "tool_name": _optional_text(payload.get("tool_name")),
        "tool_args": _object(payload.get("tool_args")),
    }
    tool_name = decision.get("tool_name")
    if tool_name is None:
        decision["next_step"] = WorkflowStep.THINK.value
        return decision
    if tool_name not in tool_names:
        allowed = ", ".join(sorted(tool_names))
        raise ValueError(f"Retrieve node requested unknown tool '{tool_name}'. Allowed tools: {allowed}.")
    if tool_name == "load_skill":
        decision["next_step"] = WorkflowStep.RETRIEVE.value
    else:
        decision["next_step"] = WorkflowStep.THINK.value
    return decision


def _think_decision(payload: dict[str, Any], *, allow_retrieve: bool) -> ThinkDecision:
    """Validate the think-node reflection payload."""
    allowed = {WorkflowStep.ANSWER.value}
    if allow_retrieve:
        allowed.add(WorkflowStep.RETRIEVE.value)
    decision: ThinkDecision = {
        **_route_decision(payload, allowed),
        "conclusion": _required_text(payload, "conclusion"),
        "update_plan": _required_text(payload, "update_plan"),
        "self_reflection": _required_text(payload, "self_reflection"),
    }
    if not allow_retrieve and decision["next_step"] == WorkflowStep.RETRIEVE.value:
        decision["next_step"] = WorkflowStep.ANSWER.value
        decision["reason"] = f"{decision['reason']} Retrieval budget is exhausted."
    return decision


def _route_decision(payload: dict[str, Any], allowed_next_steps: set[str]) -> RouteDecision:
    """Validate a simple next-step decision."""
    next_step = _required_text(payload, "next_step").lower()
    if next_step not in allowed_next_steps:
        allowed = ", ".join(sorted(allowed_next_steps))
        raise ValueError(f"Workflow node returned invalid next_step '{next_step}'. Allowed: {allowed}.")
    return {
        "next_step": next_step,
        "reason": _required_text(payload, "reason"),
    }


async def _run_tool(
    tools: tuple[BaseTool, ...],
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    """Execute one workflow tool and normalize exceptions into tool payloads."""
    tool = next((item for item in tools if item.name == tool_name), None)
    if tool is None:
        raise ValueError(f"Workflow tool '{tool_name}' is not configured.")
    try:
        result = await tool.ainvoke(tool_args)
    except Exception as exc:
        result = {
            "type": "error",
            "skill_name": tool_name,
            "items": [],
            "error": str(exc),
        }
    return result if isinstance(result, dict) else {"type": "context", "skill_name": tool_name, "items": [{"content": str(result)}]}


def _context_items_from_tool(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Read context items from a tool result."""
    if not isinstance(result, dict) or result.get("type") != "context":
        return []
    items = result.get("items")
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            item = {"content": str(item)}
        content = " ".join(str(item.get("content", item.get("document", ""))).split())
        if not content:
            continue
        normalized.append(
            {
                "title": str(item.get("title", "")).strip(),
                "content": content,
                "url": _optional_text(item.get("url")),
                "file_path": _optional_text(item.get("file_path")),
                "source_type": _optional_text(item.get("source_type")),
                "skill_name": _optional_text(result.get("skill_name")),
                "distance": item.get("distance") if isinstance(item.get("distance"), (int, float)) else None,
            }
        )
    return normalized


def _loaded_skills_from_tool(result: dict[str, Any] | None) -> list[dict[str, str]]:
    """Read skill documents from a tool result."""
    if not isinstance(result, dict) or result.get("type") != "skill":
        return []
    name = _optional_text(result.get("skill_name"))
    content = _optional_text(result.get("content"))
    if not name or not content:
        return []
    return [{"name": name, "content": content}]


def _merge_context_items(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge context items without duplicating the same content."""
    merged = [dict(item) for item in existing]
    seen = {
        (
            str(item.get("title", "")),
            str(item.get("content", "")),
            str(item.get("url", "")),
            str(item.get("file_path", "")),
        )
        for item in merged
    }
    for item in new_items:
        key = (
            str(item.get("title", "")),
            str(item.get("content", "")),
            str(item.get("url", "")),
            str(item.get("file_path", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(item))
    return merged


def _merge_loaded_skills(existing: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge loaded skill documents by normalized name."""
    merged = [dict(item) for item in existing]
    index = {str(item.get("name", "")).strip().lower(): position for position, item in enumerate(merged)}
    for item in new_items:
        name = str(item.get("name", "")).strip()
        content = str(item.get("content", "")).strip()
        if not name or not content:
            continue
        key = name.lower()
        payload = {"name": name, "content": content}
        if key in index:
            merged[index[key]] = payload
        else:
            index[key] = len(merged)
            merged.append(payload)
    return merged


def _append_trace(state: WorkflowState, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Append one workflow trace item."""
    trace = [dict(item) for item in state.get("trace", [])]
    trace.append(entry)
    return trace


def _route_detail(decision: RouteDecision) -> str:
    """Build one route detail string for tracker logs."""
    return f"Selected '{decision['next_step']}'. {decision['reason']}"


def _retrieve_detail(
    decision: RetrieveDecision,
    next_step: str,
    reason: str,
    tool_result: dict[str, Any] | None,
) -> str:
    """Build the retrieve detail string for tracker logs."""
    tool_name = decision.get("tool_name")
    if not tool_name:
        return f"Skipped tool execution and selected '{next_step}'. {reason}"
    summary = _summarize_tool_result(tool_result)
    if summary.get("error"):
        return f"Called '{tool_name}' and selected '{next_step}'. {reason} Tool error: {summary['error']}"
    extra = []
    if summary.get("skill_name"):
        extra.append(f"skill={summary['skill_name']}")
    if summary.get("count") is not None:
        extra.append(f"count={summary['count']}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    return f"Called '{tool_name}' and selected '{next_step}'. {reason}{suffix}"


def _think_detail(decision: ThinkDecision) -> str:
    """Build the think detail string for tracker logs."""
    return (
        f"Selected '{decision['next_step']}'. "
        f"Conclusion: {decision['conclusion']} "
        f"Plan: {decision['update_plan']} "
        f"Reflection: {decision['self_reflection']}"
    )


def _summarize_tool_result(result: dict[str, Any] | None) -> dict[str, Any]:
    """Build a compact tool-result summary for workflow trace persistence."""
    if not isinstance(result, dict):
        return {}
    count = result.get("count")
    if not isinstance(count, int):
        items = result.get("items")
        count = len(items) if isinstance(items, list) else None
    return {
        "type": _optional_text(result.get("type")),
        "skill_name": _optional_text(result.get("skill_name")),
        "count": count,
        "error": _optional_text(result.get("error")),
    }


def _next_step(state: WorkflowState, allowed: set[str]) -> str:
    """Read and validate the next step."""
    next_step = state["next_step"]
    if next_step not in allowed:
        joined = ", ".join(sorted(allowed))
        raise ValueError(f"Workflow next_step '{next_step}' is invalid. Allowed: {joined}.")
    return next_step


def _json_object(content: str | None) -> dict[str, Any]:
    """Parse the first JSON object from model output."""
    if content is None:
        raise ValueError("Workflow node returned empty content.")
    content = content.strip()
    if not content:
        raise ValueError("Workflow node returned an empty decision.")
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"Workflow node did not return JSON: {content}")
    try:
        payload = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Workflow node returned invalid JSON: {content}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Workflow node decision must be a JSON object.")
    return payload


def _required_text(payload: dict[str, Any], key: str) -> str:
    """Read one required string field."""
    value = " ".join(str(payload.get(key, "")).split())
    if not value:
        raise ValueError(f"Workflow node decision is missing '{key}'.")
    return value


def _optional_text(value: Any) -> str | None:
    """Normalize optional string-like values."""
    text = " ".join(str(value or "").split())
    return text or None


def _object(value: Any) -> dict[str, Any]:
    """Normalize one optional JSON object."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError("Workflow node field 'tool_args' must be a JSON object.")
