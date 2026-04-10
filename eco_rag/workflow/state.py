from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from ..skills.manager import extract_requested_skill


class WorkflowStatus(str, Enum):
    """Define the high-level workflow lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(str, Enum):
    """Name the workflow nodes exposed to the app."""

    PLAN = "plan"
    INJECT_SKILLS = "inject_skills"
    RETRIEVE = "retrieve"
    THINK = "think"
    ANSWER = "answer"


class WorkflowSkill(TypedDict):
    """Store one loaded skill document."""

    name: str
    content: str


class WorkflowContextItem(TypedDict, total=False):
    """Store one retrieved context item."""

    title: str
    content: str
    url: str | None
    file_path: str | None
    source_type: str | None
    distance: float | None
    skill_name: str | None


class WorkflowTraceEntry(TypedDict, total=False):
    """Persist one workflow node output for UI replay."""

    node: str
    output: str
    decision: dict[str, Any]
    tool_result: dict[str, Any]


class WorkflowState(TypedDict, total=False):
    """Store the mutable workflow state."""

    query: str
    context: list[dict[str, Any]]
    requested_skill: str | None
    next_step: str | None
    retrieve_count: int
    skill_load_count: int
    skills_prompt: str
    loaded_skills: list[WorkflowSkill]
    context_items: list[WorkflowContextItem]
    trace: list[WorkflowTraceEntry]
    answer: str
    token_usage: dict[str, Any] | None
    last_node: str | None
    last_detail: str | None


def new_state(query: str, context: list[dict[str, Any]] | None = None) -> WorkflowState:
    """Create the initial workflow state for one query."""
    requested_skill, cleaned_query = extract_requested_skill(query)
    base_context = list(context) if context is not None else [{"role": "user", "content": cleaned_query}]
    if context is not None and requested_skill:
        for index in range(len(base_context) - 1, -1, -1):
            item = base_context[index]
            if str(item.get("role", "")).strip() != "user":
                continue
            if " ".join(str(item.get("content", "")).strip().split()) != query:
                continue
            base_context[index] = {**item, "content": cleaned_query}
            break
    return {
        "query": cleaned_query,
        "context": base_context,
        "requested_skill": requested_skill,
        "next_step": WorkflowStep.PLAN.value,
        "retrieve_count": 0,
        "skill_load_count": 0,
        "skills_prompt": "",
        "loaded_skills": [],
        "context_items": [],
        "trace": [],
        "answer": "",
        "token_usage": None,
        "last_node": None,
        "last_detail": None,
    }


def merge_token_usage(*items: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge token usage across multiple model calls."""
    usage: dict[str, int | float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[key] = usage.get(key, 0) + value
    return usage or None
