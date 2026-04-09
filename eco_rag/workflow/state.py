from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class WorkflowStatus(str, Enum):
    """Define the high-level workflow lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStep(str, Enum):
    """Name the workflow nodes exposed to the app."""

    PLAN = "plan"
    RETRIEVE = "retrieve"
    THINK = "think"
    ANSWER = "answer"


class WorkflowState(TypedDict, total=False):
    """Store the mutable workflow state."""

    query: str
    context: list[dict[str, Any]]
    next_step: str | None
    retrieve_count: int
    context_items: list[dict[str, Any]]
    answer: str
    token_usage: dict[str, Any] | None
    last_node: str | None
    last_detail: str | None


def new_state(query: str, context: list[dict[str, Any]] | None = None) -> WorkflowState:
    """Create the initial workflow state for one query."""
    return {
        "query": query,
        "context": list(context) if context is not None else [{"role": "user", "content": query}],
        "next_step": WorkflowStep.PLAN.value,
        "retrieve_count": 0,
        "context_items": [],
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
