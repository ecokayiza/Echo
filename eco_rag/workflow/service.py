from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Callable

from ..chat.registry import ChatModelSettings, build_chat_model
from ..skills import list_available_skills
from ..settings import load_app_settings
from ..tools import build_retrieve_tools
from .drafts import WorkflowDraftStore
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
        draft_storage: dict[str, dict[str, Any]] | None = None,
        draft_base_dir: str | Path | None = None,
    ):
        self.model_factory = model_factory
        self.tool_runner = tool_runner
        self.drafts = WorkflowDraftStore(storage=draft_storage, base_dir=draft_base_dir)

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
            session_id=None,
            user_message_id=None,
        ):
            yield item

    async def stream_chat(
        self,
        question: str,
        *,
        context: list[dict[str, Any]] | None = None,
        session_id: str | None = None,
        user_message_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream workflow events for one chat turn, resuming when a live draft exists."""
        query = self._query(question)
        state, tracker, records = self._load_or_create_state(
            query,
            context=context,
            session_id=session_id,
            user_message_id=user_message_id,
        )
        async for item in self._stream_state(
            state,
            tracker=tracker,
            records=records,
            session_id=session_id,
            user_message_id=user_message_id,
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

    def _load_or_create_state(
        self,
        query: str,
        *,
        context: list[dict[str, Any]] | None,
        session_id: str | None,
        user_message_id: str | None,
    ) -> tuple[WorkflowState, WorkflowTracker, list[dict[str, Any]]]:
        """Load a resumable draft or create a fresh workflow state."""
        if session_id and user_message_id:
            draft = self.drafts.load(session_id)
            if draft is not None and draft["user_message_id"] == user_message_id:
                state = dict(draft["state"])
                if "workflow_memory" not in state:
                    self.drafts.clear(session_id)
                else:
                    tracker = WorkflowTracker.from_snapshot(draft["snapshot"], query=state["query"])
                    tracker.log("Workflow resumed from the saved live draft.")
                    self.drafts.persist(
                        session_id,
                        user_message_id=user_message_id,
                        state=state,
                        snapshot=tracker.snapshot(state),
                        records=draft["records"],
                    )
                    return state, tracker, list(draft["records"])
            if draft is not None:
                self.drafts.clear(session_id)

        state = new_state(query, self._default_context(query, context), workflow_turn_id=user_message_id)
        tracker = WorkflowTracker(state["workflow_turn_id"], state["query"])
        if session_id and user_message_id:
            self.drafts.persist(
                session_id,
                user_message_id=user_message_id,
                state=state,
                snapshot=tracker.snapshot(state),
                records=[],
            )
        return state, tracker, []

    async def _stream_state(
        self,
        state: WorkflowState,
        *,
        tracker: WorkflowTracker | None,
        records: list[dict[str, Any]],
        session_id: str | None,
        user_message_id: str | None,
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
                    elif payload.get("event") == "record" and isinstance(payload.get("data"), dict):
                        buffered_records.append(dict(payload["data"]))
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
                self._persist_draft(
                    session_id=session_id,
                    user_message_id=user_message_id,
                    state=current_state,
                    tracker=runtime_tracker,
                    records=buffered_records,
                )
                yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}

            runtime_tracker.finish()
            snapshot = runtime_tracker.snapshot(current_state)
            yield {"event": "state", "data": snapshot}
            if session_id:
                self.drafts.clear(session_id)
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
            self._persist_draft(
                session_id=session_id,
                user_message_id=user_message_id,
                state=current_state,
                tracker=runtime_tracker,
                records=buffered_records,
            )
            yield {"event": "state", "data": runtime_tracker.snapshot(current_state)}
            raise

    def _persist_draft(
        self,
        *,
        session_id: str | None,
        user_message_id: str | None,
        state: WorkflowState,
        tracker: WorkflowTracker,
        records: list[dict[str, Any]],
    ):
        """Persist the current live workflow draft when resumable ids are available."""
        if not session_id or not user_message_id:
            return
        self.drafts.persist(
            session_id,
            user_message_id=user_message_id,
            state=state,
            snapshot=tracker.snapshot(state),
            records=records,
        )

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
            detail = "Choosing the next step."
        elif step == WorkflowStep.RETRIEVE:
            detail = "Preparing the retrieve step."
        elif step == WorkflowStep.TOOL:
            detail = "Running the tool."
        elif step == WorkflowStep.THINK:
            detail = "Reasoning over the tool results."
        elif step == WorkflowStep.ANSWER:
            detail = "Publishing the final answer."
        tracker.start(step, detail)


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
    return f"Selected '{step}'." if step else "Selected the next step."
