from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from .nodes import (
    WorkflowDependencies,
    answer_node,
    plan_node,
    retrieve_node,
    route_after_plan,
    route_after_retrieve,
    route_after_think,
    route_after_tool,
    think_node,
    tool_node,
)
from .state import WorkflowState, WorkflowStep


def build_workflow(deps: WorkflowDependencies):
    """Build the LangGraph workflow for one runtime configuration."""
    graph = StateGraph(WorkflowState)
    graph.add_node(WorkflowStep.PLAN.value, partial(plan_node, deps=deps))
    graph.add_node(WorkflowStep.RETRIEVE.value, retrieve_node)
    graph.add_node(WorkflowStep.TOOL.value, partial(tool_node, deps=deps))
    graph.add_node(WorkflowStep.THINK.value, partial(think_node, deps=deps))
    graph.add_node(WorkflowStep.ANSWER.value, answer_node)
    graph.add_edge(START, WorkflowStep.PLAN.value)
    graph.add_conditional_edges(
        WorkflowStep.PLAN.value,
        route_after_plan,
        {
            WorkflowStep.RETRIEVE.value: WorkflowStep.RETRIEVE.value,
            WorkflowStep.ANSWER.value: WorkflowStep.ANSWER.value,
        },
    )
    graph.add_conditional_edges(
        WorkflowStep.RETRIEVE.value,
        route_after_retrieve,
        {
            WorkflowStep.TOOL.value: WorkflowStep.TOOL.value,
        },
    )
    graph.add_conditional_edges(
        WorkflowStep.TOOL.value,
        route_after_tool,
        {
            WorkflowStep.THINK.value: WorkflowStep.THINK.value,
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
