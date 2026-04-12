from __future__ import annotations

from typing import Any, AsyncIterator, Callable

from ..chat.registry import ChatModelSettings, build_chat_model
from ..skills import list_available_skills
from ..settings import load_app_settings
from ..tools import build_retrieve_tools
from .graph import build_workflow
from .nodes import WorkflowDependencies
from .prompts import default_system_prompt
from .state import WorkflowState, WorkflowStep, new_state
from .tracker import WorkflowTracker


class WorkflowService:
    """Run the LangGraph workflow and adapt it to the app stream contract."""

    def __init__(
        self,
        model_factory: Callable[[ChatModelSettings | None], Any] = build_chat_model,
        *,
        tool_runner: Callable[[str], Any] | None = None,
    ):
        self.model_factory = model_factory
        self.tool_runner = tool_runner

    async def stream(
        self,
        question: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream workflow events for one standalone question."""
        query = self._query(question)
        async for item in self._stream_state(
            new_state(query, self._default_context(query)),
            tracker=None,
            records=[],
        ):
            yield item

    async def stream_chat(
        self,
        question: str,
        *,
        context: list[dict[str, Any]] | None = None,
        workflow_turn_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream workflow events for one chat turn from persisted session history."""
        query = self._query(question)
        async for item in self._stream_state(
            new_state(query, self._default_context(query, context), workflow_turn_id=workflow_turn_id),
            tracker=None,
            records=[],
        ):
            yield item

    def _deps(self) -> WorkflowDependencies:
        """Build one dependency bundle for a workflow run."""
        settings = load_app_settings()
        return WorkflowDependencies(
            model=self.model_factory(),
            retrieve_tools=tuple(build_retrieve_tools(self.tool_runner)),
            max_retrieve_rounds=settings.max_retrieve_rounds,
        )

    def _default_context(self, query: str, context: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Ensure the workflow transcript starts with one rendered system prompt."""
        base_context = [dict(item) for item in (context or []) if isinstance(item, dict)]
        if not any(str(item.get("role", "")).strip() == "system" for item in base_context):
            base_context.insert(
                0,
                {
                    "role": "system",
                    "content": default_system_prompt(
                        available_skills=list_available_skills(),
                        available_tools=[tool.name for tool in build_retrieve_tools(self.tool_runner)],
                    ),
                },
            )
        if not any(str(item.get("role", "")).strip() == "user" for item in base_context):
            base_context.append({"role": "user", "content": query})
        return base_context

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
        *,
        tracker: WorkflowTracker | None,
        records: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the workflow and emit state updates, chunks, and the final result."""
        deps = self._deps()
        graph = build_workflow(deps)
        runtime_tracker = tracker or WorkflowTracker(state["workflow_turn_id"], state["query"])
        current_state = dict(state)
        buffered_records = [dict(item) for item in records]
        yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}

        try:
            async for mode, payload in graph.astream(current_state, stream_mode=["tasks", "custom"]):
                if mode == "custom":
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("event") == "chunk":
                        yield payload
                    elif payload.get("event") == "transition" and isinstance(payload.get("data"), dict):
                        self._apply_transition(runtime_tracker, current_state, payload["data"])
                        yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}
                    elif payload.get("event") == "record" and isinstance(payload.get("data"), dict):
                        record = dict(payload["data"])
                        persist = bool(record.pop("persist", True))
                        if persist:
                            buffered_records.append(dict(record))
                        yield {"event": "record", "data": record}
                    continue

                if mode != "tasks" or not isinstance(payload, dict):
                    continue

                node_name = payload.get("name")
                if node_name not in {step.value for step in WorkflowStep}:
                    continue

                step = WorkflowStep(node_name)
                if "input" in payload:
                    self._start_step(runtime_tracker, step)
                    yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}
                    continue

                if payload.get("error") is not None:
                    continue

                result = payload.get("result")
                if isinstance(result, dict):
                    current_state = {**current_state, **result}
                runtime_tracker.complete(step, self._detail_for_step(step, current_state))
                self._log_route(runtime_tracker, step, current_state)
                yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}

            runtime_tracker.finish()
            snapshot = runtime_tracker.snapshot(current_state)
            yield {"event": "state", "data": snapshot}
            yield {
                "event": "done",
                "data": {
                    "snapshot": snapshot,
                    "records": buffered_records,
                    "token_usage": _sum_token_usage(buffered_records),
                },
            }
        except Exception as exc:
            runtime_tracker.fail(str(exc), node=runtime_tracker.active_node)
            yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}
            raise

    @staticmethod
    def _detail_for_step(step: WorkflowStep, state: WorkflowState) -> str:
        """Build one compact completion detail for the workflow tracker."""
        if step == WorkflowStep.PLAN:
            return _route_detail(state.get("next_step"))
        if step == WorkflowStep.RETRIEVE:
            pending = state.get("pending_retrieve") or {}
            tool_name = str(pending.get("name") or "").strip()
            return f"Accepted '{tool_name}'." if tool_name else "Accepted the pending retrieve command."
        if step == WorkflowStep.TOOL:
            return f"Completed round {state['retrieve_round']}."
        if step == WorkflowStep.THINK:
            return _route_detail(state.get("next_step"))
        return "Final answer emitted."

    @staticmethod
    def _log_route(tracker: WorkflowTracker, step: WorkflowStep, state: WorkflowState):
        """Keep live workflow logs minimal and high-signal."""
        if step == WorkflowStep.RETRIEVE:
            pending = state.get("pending_retrieve") or {}
            tool_name = str(pending.get("name") or "").strip()
            if tool_name:
                tracker.log(f"Using '{tool_name}'.", node=step.value)

    @staticmethod
    def _start_step(tracker: WorkflowTracker, step: WorkflowStep):
        """Mark one workflow step as running with simple UI-facing detail."""
        detail = None
        if step == WorkflowStep.PLAN:
            detail = "Planning the response."
        elif step == WorkflowStep.RETRIEVE:
            detail = "Preparing the retrieve step."
        elif step == WorkflowStep.TOOL:
            detail = "Running the tool."
        elif step == WorkflowStep.THINK:
            detail = "Reviewing the tool results."
        elif step == WorkflowStep.ANSWER:
            detail = "Publishing the final answer."
        tracker.start(step, detail)

    @staticmethod
    def _apply_transition(tracker: WorkflowTracker, state: WorkflowState, payload: dict[str, Any]):
        """Reflect one live routing hint before the current node fully completes."""
        target = str(payload.get("to_node") or "").strip()
        if target != WorkflowStep.ANSWER.value:
            return

        source = str(payload.get("from_node") or "").strip()
        if source in {WorkflowStep.PLAN.value, WorkflowStep.THINK.value}:
            tracker.complete(WorkflowStep(source), _route_detail(WorkflowStep.ANSWER.value))
        answer = str(payload.get("answer") or "").strip()
        if answer:
            state["prepared_answer"] = answer
            state["streamed_answer"] = answer
        tracker.start(WorkflowStep.ANSWER, "Publishing the final answer.")


def _sum_token_usage(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate token usage across buffered workflow records."""
    usage: dict[str, int | float] = {}
    for record in records:
        token_usage = record.get("token_usage")
        if not isinstance(token_usage, dict):
            continue
        for key, value in token_usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[key] = usage.get(key, 0) + value
    return usage or None


def _route_detail(next_step: Any) -> str:
    """Render a short route detail for decision nodes."""
    step = str(next_step or "").strip()
    if step == WorkflowStep.RETRIEVE.value:
        return "Will retrieve more context."
    if step == WorkflowStep.ANSWER.value:
        return "Answer is ready."
    return "Decision completed."
