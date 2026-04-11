import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import type { WorkflowSnapshot } from "@/types/chat";
import { WorkflowGraph } from "./WorkflowGraph";

interface WorkflowPanelProps {
  workflow: WorkflowSnapshot | null;
}

export function WorkflowPanel({ workflow }: WorkflowPanelProps) {
  if (!workflow) {
    return (
      <SectionCard eyebrow="Workflow">
        <EmptyState
          title="No Live Workflow"
          description="Run a message to see the current LangGraph route here while it is in flight."
        />
      </SectionCard>
    );
  }

  return (
    <SectionCard eyebrow="Workflow">
      <div aria-label="Workflow modern graph" style={{ padding: "20px 0" }}>
        <WorkflowGraph nodes={workflow.node_statuses} activeNode={workflow.active_node || null} />
      </div>

      <div className="workflow-copy">
        <span className="workflow-copy__label">Query</span>
        <p>{workflow.query}</p>
      </div>

      <div className="workflow-copy">
        <span className="workflow-copy__label">Result</span>
        <p>{workflow.errors.length > 0 ? workflow.errors.join(" ") : workflow.answer || workflow.status}</p>
      </div>
    </SectionCard>
  );
}
