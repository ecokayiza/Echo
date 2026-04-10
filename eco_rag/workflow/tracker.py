from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import WorkflowState, WorkflowStatus, WorkflowStep


@dataclass
class WorkflowTracker:
    """Track node state, logs, and errors for one workflow run."""

    query: str

    def __post_init__(self):
        """Initialize the mutable tracking fields."""
        self.status = WorkflowStatus.RUNNING.value
        self.active_node: str | None = WorkflowStep.PLAN.value
        self.node_statuses = [
            {"node": step.value, "status": WorkflowStatus.QUEUED.value, "detail": None}
            for step in WorkflowStep
        ]
        self.logs: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._set(WorkflowStep.PLAN.value, WorkflowStatus.RUNNING.value, "Preparing workflow.")

    def start(self, node: WorkflowStep, detail: str | None = None):
        """Mark one node as running."""
        self.status = WorkflowStatus.RUNNING.value
        self.active_node = node.value
        self._set(node.value, WorkflowStatus.RUNNING.value, detail)
        self.log(f"{node.value} started.", node=node.value)

    def complete(self, node: WorkflowStep, detail: str):
        """Mark one node as completed."""
        self._set(node.value, WorkflowStatus.COMPLETED.value, detail)
        self.log(detail, node=node.value)

    def skip(self, node: WorkflowStep, detail: str):
        """Mark one node as skipped."""
        current = self._get(node.value)
        if current["status"] != WorkflowStatus.QUEUED.value:
            return
        self._set(node.value, "skipped", detail)
        self.log(detail, node=node.value)

    def log(self, message: str, *, node: str | None = None, level: str = "info"):
        """Append one workflow log message."""
        self.logs.append({"level": level, "node": node, "message": message})

    def fail(self, error: str, *, node: str | None = None):
        """Mark the workflow as failed."""
        self.status = WorkflowStatus.FAILED.value
        self.active_node = None
        self.errors.append(error)
        if node is not None:
            current = self._get(node)
            self._set(node, "failed", current["detail"] or error)
        self.log(error, node=node, level="error")

    def finish(self):
        """Mark the workflow as completed and finalize skipped nodes."""
        self.status = WorkflowStatus.COMPLETED.value
        self.active_node = None
        for item in self.node_statuses:
            if item["status"] == WorkflowStatus.QUEUED.value:
                item["status"] = "skipped"
                item["detail"] = "This node was not needed in the final route."

    def snapshot(self, state: WorkflowState) -> dict[str, Any]:
        """Build the UI-facing workflow snapshot."""
        return {
            "query": state["query"],
            "requested_skill": state.get("requested_skill"),
            "loaded_skills": list(state.get("loaded_skills", [])),
            "context_items": list(state["context_items"]),
            "trace": list(state.get("trace", [])),
            "answer": state["answer"],
            "token_usage": state["token_usage"],
            "status": self.status,
            "active_node": self.active_node,
            "node_statuses": [dict(item) for item in self.node_statuses],
            "logs": [dict(item) for item in self.logs],
            "errors": list(self.errors),
        }

    def _get(self, node: str) -> dict[str, Any]:
        """Return the mutable status entry for one node."""
        return next(item for item in self.node_statuses if item["node"] == node)

    def _set(self, node: str, status: str, detail: str | None):
        """Replace the tracked status for one node."""
        item = self._get(node)
        item["status"] = status
        item["detail"] = detail
