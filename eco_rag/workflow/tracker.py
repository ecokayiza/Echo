from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import WorkflowState, WorkflowStatus, WorkflowStep


@dataclass
class WorkflowTracker:
    """Track minimal workflow status for UI updates and resume support."""

    workflow_turn_id: str
    query: str

    def __post_init__(self):
        self.status = WorkflowStatus.RUNNING.value
        self.active_node: str | None = WorkflowStep.PLAN.value
        self.node_statuses = [
            {"node": step.value, "status": WorkflowStatus.QUEUED.value, "detail": None}
            for step in WorkflowStep
        ]
        self.logs: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._set(WorkflowStep.PLAN.value, WorkflowStatus.RUNNING.value, "Planning the next action.")

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any], *, query: str) -> WorkflowTracker:
        """Rebuild the tracker from a saved workflow snapshot."""
        workflow_turn_id = str(snapshot.get("workflow_turn_id") or "").strip()
        tracker = cls(workflow_turn_id=workflow_turn_id, query=query)
        tracker.status = str(snapshot.get("status") or WorkflowStatus.RUNNING.value)
        active_node = snapshot.get("active_node")
        tracker.active_node = str(active_node) if active_node is not None else None
        node_statuses = snapshot.get("node_statuses")
        logs = snapshot.get("logs")
        errors = snapshot.get("errors")
        if isinstance(node_statuses, list) and len(node_statuses) == len(tracker.node_statuses):
            tracker.node_statuses = [dict(item) for item in node_statuses if isinstance(item, dict)]
        if isinstance(logs, list):
            tracker.logs = [dict(item) for item in logs if isinstance(item, dict)]
        if isinstance(errors, list):
            tracker.errors = [str(item) for item in errors]
        return tracker

    def start(self, node: WorkflowStep, detail: str | None = None):
        """Mark one node as running."""
        self.status = WorkflowStatus.RUNNING.value
        self.active_node = node.value
        self._set(node.value, WorkflowStatus.RUNNING.value, detail)

    def complete(self, node: WorkflowStep, detail: str):
        """Mark one node as completed."""
        self._set(node.value, WorkflowStatus.COMPLETED.value, detail)

    def skip(self, node: WorkflowStep, detail: str):
        """Mark one node as skipped."""
        current = self._get(node.value)
        if current["status"] != WorkflowStatus.QUEUED.value:
            return
        self._set(node.value, "skipped", detail)

    def log(self, message: str, *, node: str | None = None, level: str = "info"):
        """Append one workflow log entry."""
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
        """Mark the workflow as completed and skip unused nodes."""
        self.status = WorkflowStatus.COMPLETED.value
        self.active_node = None
        for item in self.node_statuses:
            if item["status"] == WorkflowStatus.QUEUED.value:
                item["status"] = "skipped"
                item["detail"] = None

    def snapshot(self, state: WorkflowState) -> dict[str, Any]:
        """Build the minimal workflow snapshot returned to the app."""
        pending = state.get("pending_retrieve") or {}
        tool_name = str(pending.get("name") or "").strip() or None
        return {
            "workflow_turn_id": state["workflow_turn_id"],
            "query": state["query"],
            "answer": state.get("prepared_answer", ""),
            "status": self.status,
            "active_node": self.active_node,
            "tool_name": tool_name,
            "node_statuses": [dict(item) for item in self.node_statuses],
            "logs": [dict(item) for item in self.logs],
            "errors": list(self.errors),
        }

    def _get(self, node: str) -> dict[str, Any]:
        return next(item for item in self.node_statuses if item["node"] == node)

    def _set(self, node: str, status: str, detail: str | None):
        item = self._get(node)
        item["status"] = status
        item["detail"] = detail
