from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict
from uuid import uuid4

from ..skills.manager import extract_requested_skill


class WorkflowStatus(str, Enum):
    """Define the workflow lifecycle exposed to the app."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(str, Enum):
    """Name the workflow nodes exposed to the app."""

    PLAN = "plan"
    RETRIEVE = "retrieve"
    TOOL = "tool"
    THINK = "think"
    ANSWER = "answer"


class WorkflowRetrieveCall(TypedDict):
    """Store one pending retrieval command."""

    name: str
    args: dict[str, Any]


class WorkflowMemoryMessage(TypedDict):
    """Store one flat in-workflow memory message."""

    role: str
    content: str


class WorkflowState(TypedDict, total=False):
    """Store the mutable workflow state."""

    workflow_turn_id: str
    query: str
    requested_skill: str | None
    next_step: str | None
    retrieve_round: int
    pending_retrieve: WorkflowRetrieveCall | None
    prepared_answer: str
    workflow_memory: list[WorkflowMemoryMessage]


def new_state(
    query: str,
    context: list[dict[str, Any]] | None = None,
    *,
    workflow_turn_id: str | None = None,
) -> WorkflowState:
    """Create the initial workflow state for one query."""
    requested_skill, cleaned_query = extract_requested_skill(query)
    base_context = _normalize_memory(context) if context is not None else [{"role": "user", "content": query}]
    return {
        "workflow_turn_id": (workflow_turn_id or str(uuid4())).strip(),
        "query": cleaned_query,
        "requested_skill": requested_skill,
        "next_step": WorkflowStep.PLAN.value,
        "retrieve_round": 0,
        "pending_retrieve": None,
        "prepared_answer": "",
        "workflow_memory": base_context,
    }


def _normalize_memory(messages: list[dict[str, Any]] | None) -> list[WorkflowMemoryMessage]:
    """Keep only provider-safe role/content pairs in workflow memory."""
    normalized: list[WorkflowMemoryMessage] = []
    for item in messages or []:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized
