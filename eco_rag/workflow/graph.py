from __future__ import annotations

from functools import partial

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .nodes import (
    WorkflowDependencies,
    answer_node_messages,
    finalize_answer_state,
    plan_node,
    retrieve_node,
    route_after_plan,
    route_after_retrieve,
    route_after_think,
    think_node,
)
from .state import WorkflowState, WorkflowStep


async def _answer_node(state: WorkflowState, deps: WorkflowDependencies):
    """Run the streaming answer node and emit token deltas through LangGraph."""
    model = deps.model_factory(deps.settings)
    writer = get_stream_writer()
    reply_parts: list[str] = []
    token_usage = None

    def on_usage(usage):
        nonlocal token_usage
        if usage is None:
            return
        token_usage = dict(usage)

    async for delta in model.stream_response(answer_node_messages(state, deps), callbacks={"on_usage": on_usage}):
        reply_parts.append(delta)
        writer({"event": "chunk", "data": {"delta": delta, "content": "".join(reply_parts)}})

    return finalize_answer_state(state, "".join(reply_parts), token_usage)


def build_workflow(deps: WorkflowDependencies):
    """Build the LangGraph workflow for one runtime configuration."""
    graph = StateGraph(WorkflowState)
    graph.add_node(WorkflowStep.PLAN.value, partial(plan_node, deps=deps))
    graph.add_node(WorkflowStep.RETRIEVE.value, partial(retrieve_node, deps=deps))
    graph.add_node(WorkflowStep.THINK.value, partial(think_node, deps=deps))
    graph.add_node(WorkflowStep.ANSWER.value, partial(_answer_node, deps=deps))
    graph.add_edge(START, WorkflowStep.PLAN.value)
    graph.add_conditional_edges(
        WorkflowStep.PLAN.value,
        route_after_plan,
        {
            WorkflowStep.RETRIEVE.value: WorkflowStep.RETRIEVE.value,
            WorkflowStep.THINK.value: WorkflowStep.THINK.value,
        },
    )
    graph.add_conditional_edges(
        WorkflowStep.RETRIEVE.value,
        route_after_retrieve,
        {
            WorkflowStep.THINK.value: WorkflowStep.THINK.value,
            WorkflowStep.ANSWER.value: WorkflowStep.ANSWER.value,
        },
    )
    graph.add_conditional_edges(
        WorkflowStep.THINK.value,
        route_after_think,
        {
            WorkflowStep.RETRIEVE.value: WorkflowStep.RETRIEVE.value,
            WorkflowStep.ANSWER.value: WorkflowStep.ANSWER.value,
        },
    )
    graph.add_edge(WorkflowStep.ANSWER.value, END)
    return graph.compile()
