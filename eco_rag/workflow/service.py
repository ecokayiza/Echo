from __future__ import annotations

from typing import AsyncIterator
from typing import Any, Callable

from ..chat.registry import ChatModelSettings, build_chat_model
from .graph import build_workflow
from .nodes import (
    DEFAULT_WORKFLOW_PROMPT,
    WorkflowDependencies,
)
from .state import WorkflowState, WorkflowStep, new_state
from .tracker import WorkflowTracker


class WorkflowService:
    """Run question answering through the workflow."""

    def __init__(
        self,
        model_factory: Callable[[ChatModelSettings | None], Any] = build_chat_model,
        *,
        tool_runner: Callable[[str], Any] | None = None,
        system_prompt: str = DEFAULT_WORKFLOW_PROMPT,
    ):
        """Store the runtime dependencies used by each workflow run."""
        self.model_factory = model_factory
        self.tool_runner = tool_runner
        self.system_prompt = system_prompt

    async def stream(
        self,
        question: str,
        settings: ChatModelSettings | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream workflow events for one standalone question."""
        async for item in self._stream_state(new_state(self._query(question)), settings):
            yield item

    async def stream_chat(
        self,
        question: str,
        *,
        context: list[dict[str, Any]] | None = None,
        settings: ChatModelSettings | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream workflow events for one chat turn."""
        async for item in self._stream_state(new_state(self._query(question), context), settings):
            yield item

    def _deps(self, settings: ChatModelSettings | None) -> WorkflowDependencies:
        """Build one dependency bundle for a workflow run."""
        return WorkflowDependencies(
            model_factory=self.model_factory,
            settings=settings,
            tool_runner=self.tool_runner,
            system_prompt=self.system_prompt,
        )

    @staticmethod
    def _query(question: str) -> str:
        """Normalize one workflow question."""
        query = " ".join(question.strip().split())
        if not query:
            raise ValueError("Question cannot be empty.")
        return query

    async def _stream_state(
        self,
        state: WorkflowState,
        settings: ChatModelSettings | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the LangGraph workflow and adapt its events to the app stream contract."""
        deps = self._deps(settings)
        graph = build_workflow(deps)
        tracker = WorkflowTracker(state["query"])
        tracker.log("Workflow created.")
        current_state = dict(state)
        yield {"event": "state", "data": tracker.snapshot(current_state)}

        try:
            async for mode, payload in graph.astream(current_state, stream_mode=["tasks", "custom"]):
                if mode == "custom":
                    if isinstance(payload, dict) and payload.get("event") == "chunk":
                        yield payload
                    continue

                if mode != "tasks" or not isinstance(payload, dict):
                    continue

                node_name = payload.get("name")
                if node_name not in {step.value for step in WorkflowStep}:
                    continue

                step = WorkflowStep(node_name)
                if "input" in payload:
                    self._start_step(tracker, step)
                    yield {"event": "state", "data": tracker.snapshot(current_state)}
                    continue

                if payload.get("error") is not None:
                    continue

                result = payload.get("result")
                if isinstance(result, dict):
                    current_state = {**current_state, **result}
                tracker.complete(step, self._detail_for_step(step, current_state))
                self._log_route(tracker, step, current_state)
                yield {"event": "state", "data": tracker.snapshot(current_state)}

            tracker.finish()
            yield {"event": "state", "data": tracker.snapshot(current_state)}
            yield {"event": "done", "data": tracker.snapshot(current_state)}
        except Exception as exc:
            tracker.fail(str(exc), node=tracker.active_node)
            yield {"event": "state", "data": tracker.snapshot(current_state)}
            raise

    @staticmethod
    def _detail_for_step(step: WorkflowStep, state: WorkflowState) -> str:
        """Read the completion detail produced by one workflow node."""
        detail = state.get("last_detail")
        if isinstance(detail, str) and detail.strip():
            return detail
        if step == WorkflowStep.ANSWER:
            return "Generated final answer."
        return f"{step.value} completed."

    @staticmethod
    def _log_route(tracker: WorkflowTracker, step: WorkflowStep, state: WorkflowState):
        """Mirror route selection logs from the graph state into tracker logs."""
        next_step = state.get("next_step")
        if step == WorkflowStep.PLAN and next_step:
            tracker.log(f"Planner selected '{next_step}'.", node=step.value)
        elif step == WorkflowStep.RETRIEVE and next_step:
            tracker.log(f"Retrieve selected '{next_step}'.", node=step.value)
        elif step == WorkflowStep.THINK and next_step:
            tracker.log(f"Think selected '{next_step}'.", node=step.value)

    @staticmethod
    def _start_step(tracker: WorkflowTracker, step: WorkflowStep):
        """Mark one workflow step as running with the UI-facing detail text."""
        if step == WorkflowStep.ANSWER and tracker._get(WorkflowStep.RETRIEVE.value)["status"] == "queued":
            tracker.skip(WorkflowStep.RETRIEVE, "This route answered without external retrieval.")
        detail = None
        if step == WorkflowStep.PLAN:
            detail = "Preparing workflow."
        elif step == WorkflowStep.ANSWER:
            detail = "Streaming final answer."
        tracker.start(step, detail)
