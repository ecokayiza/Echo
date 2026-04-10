import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import type { WorkflowNodeStatus, WorkflowSnapshot } from "@/types/chat";
import { WorkflowGraph } from "./WorkflowGraph";

interface WorkflowPanelProps {
  workflow: WorkflowSnapshot | null;
}

export function WorkflowPanel({ workflow }: WorkflowPanelProps) {
  return (
    <SectionCard
      eyebrow="Trace"
    >
      <div aria-label="Workflow modern graph" style={{ padding: "20px 0" }}>
        <WorkflowGraph nodes={workflow?.node_statuses || []} activeNode={workflow?.active_node || null} />
      </div>

      {workflow && (
        <>
          <div className="workflow-copy">
            <span className="workflow-copy__label">Query</span>
            <p>{workflow.query}</p>
          </div>

          <div className="workflow-copy">
            <span className="workflow-copy__label">Logs</span>
            <div className="workflow-log-list">
              {workflow.logs.map((log, index) => (
                <p className="workflow-log-list__item" key={`${log.level}-${log.node}-${index}`}>
                  [{log.level}]
                  {log.node ? ` ${log.node}: ` : " "}
                  {log.message}
                </p>
              ))}
            </div>
          </div>

          <div className="workflow-copy">
            <span className="workflow-copy__label">Result</span>
            <p>{workflow.errors.length > 0 ? workflow.errors.join(" ") : workflow.answer}</p>
          </div>
        </>
      )}
    </SectionCard>
  );
}
