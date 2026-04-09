from __future__ import annotations

import json
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Awaitable, Callable

from ..chat.registry import ChatModelSettings, build_chat_model
from .prompts import answer_messages, plan_messages, retrieve_messages, think_messages
from .state import WorkflowState, WorkflowStep, merge_token_usage

ToolRunner = Callable[[str], Any]
ModelFactory = Callable[[ChatModelSettings | None], Any]
DEFAULT_WORKFLOW_PROMPT = "You are the chat assistant for Eco_RAG."


@dataclass(frozen=True)
class WorkflowDependencies:
    """Bind runtime dependencies to one workflow instance."""

    model_factory: ModelFactory = build_chat_model
    settings: ChatModelSettings | None = None
    tool_runner: ToolRunner | None = None
    system_prompt: str = DEFAULT_WORKFLOW_PROMPT
    max_retrieve_count: int = 2


async def plan_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Choose the first workflow action."""
    model = deps.model_factory(deps.settings)
    decision, usage = await _decision(
        model,
        plan_messages(state["query"], state["context"], deps.tool_runner is not None),
        {"retrieve", "think"},
    )
    return {
        **state,
        "next_step": decision["next_step"],
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.PLAN.value,
        "last_detail": decision["reason"],
    }


async def retrieve_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Collect external context, then choose the next action."""
    if deps.tool_runner is None:
        raise ValueError("Retrieve node requires a tool runner.")

    context_items = _context_items(await _resolve(deps.tool_runner(state["query"])))
    model = deps.model_factory(deps.settings)
    decision, usage = await _decision(
        model,
        retrieve_messages(state["query"], context_items),
        {"think", "answer"},
    )
    return {
        **state,
        "context_items": context_items,
        "next_step": decision["next_step"],
        "retrieve_count": state["retrieve_count"] + 1,
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.RETRIEVE.value,
        "last_detail": f"Collected {len(context_items)} external context item(s). {decision['reason']}",
    }


async def think_node(state: WorkflowState, deps: WorkflowDependencies) -> WorkflowState:
    """Judge whether to answer now or retrieve again."""
    allow_retrieve = deps.tool_runner is not None and state["retrieve_count"] < deps.max_retrieve_count
    model = deps.model_factory(deps.settings)
    decision, usage = await _decision(
        model,
        think_messages(
            state["query"],
            state["context"],
            state["context_items"],
            allow_retrieve,
        ),
        {"retrieve", "answer"} if allow_retrieve else {"answer"},
    )
    return {
        **state,
        "next_step": decision["next_step"],
        "token_usage": merge_token_usage(state["token_usage"], usage),
        "last_node": WorkflowStep.THINK.value,
        "last_detail": decision["reason"],
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
    }


def route_after_plan(state: WorkflowState) -> str:
    """Read the next node after plan."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.THINK.value})


def route_after_retrieve(state: WorkflowState) -> str:
    """Read the next node after retrieve."""
    return _next_step(state, {WorkflowStep.THINK.value, WorkflowStep.ANSWER.value})


def route_after_think(state: WorkflowState) -> str:
    """Read the next node after think."""
    return _next_step(state, {WorkflowStep.RETRIEVE.value, WorkflowStep.ANSWER.value})


async def _decision(model: Any, messages: list[dict[str, str]], allowed_next_steps: set[str]) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Call the LLM and parse one workflow action decision."""
    response = await model.generate_response(messages)
    payload = _json_object(response.content)
    next_step = str(_required(payload, "next_step")).strip().lower()
    if next_step not in allowed_next_steps:
        allowed = ", ".join(sorted(allowed_next_steps))
        raise ValueError(f"Workflow node returned invalid next_step '{next_step}'. Allowed: {allowed}.")
    reason = " ".join(str(_required(payload, "reason")).split())
    if not reason:
        raise ValueError("Workflow node returned an empty reason.")
    return {"next_step": next_step, "reason": reason}, response.token_usage


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


def _required(payload: dict[str, Any], key: str) -> Any:
    """Read one required JSON field."""
    if key not in payload:
        raise ValueError(f"Workflow node decision is missing '{key}'.")
    return payload[key]


async def _resolve(value: Awaitable[Any] | Any) -> Any:
    """Await async dependencies and pass through sync values."""
    return await value if isawaitable(value) else value


def _context_items(items: Any) -> list[dict[str, Any]]:
    """Normalize tool results into plain dictionaries."""
    context_items: list[dict[str, Any]] = []
    for item in items or []:
        if hasattr(item, "model_dump"):
            context_items.append(item.model_dump())
        elif isinstance(item, dict):
            context_items.append(item)
        else:
            context_items.append({"content": str(item)})
    return context_items
