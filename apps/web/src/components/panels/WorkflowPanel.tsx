import { SectionCard } from "@/components/common/SectionCard";
import type { WorkflowSnapshot } from "@/types/chat";
import { WorkflowGraph } from "./WorkflowGraph";

interface WorkflowPanelProps {
  workflow: WorkflowSnapshot | null;
}

export function WorkflowPanel({ workflow }: WorkflowPanelProps) {
  const logEntries = workflow ? buildWorkflowLogEntries(workflow) : [];

  return (
    <SectionCard eyebrow="Workflow">
      <div aria-label="Workflow modern graph" style={{ padding: "20px 0" }}>
        <WorkflowGraph
          nodes={workflow?.node_statuses ?? []}
          activeNode={workflow?.active_node || null}
          toolName={workflow?.tool_name || null}
        />
      </div>

      {workflow ? (
        <>
          <div className="workflow-copy">
            <span className="workflow-copy__label">Query</span>
            <p>{workflow.query}</p>
          </div>

          <div className="workflow-copy">
            <span className="workflow-copy__label">Result</span>
            <p>{workflow.errors.length > 0 ? workflow.errors.join(" ") : workflow.answer || workflow.status}</p>
          </div>

          {logEntries.length > 0 ? (
            <div className="workflow-copy">
              <span className="workflow-copy__label">Logs</span>
              <div className="workflow-log-list">
                {logEntries.map((entry, index) => (
                  <div key={`${entry.label}-${index}`} className="workflow-log-list__item">
                    <strong>[{entry.label}]</strong> {entry.message}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </SectionCard>
  );
}

function buildWorkflowLogEntries(workflow: WorkflowSnapshot) {
  const stepEntries = workflow.node_statuses
    .filter((node) => node.detail)
    .map((node) => ({
      label: node.node,
      message: String(node.detail).trim(),
    }));

  const extraEntries = workflow.logs
    .filter((entry) => entry.message)
    .map((entry) => ({
      label: entry.node || entry.level || "log",
      message: String(entry.message).trim(),
    }));

  const seen = new Set<string>();
  return [...stepEntries, ...extraEntries].filter((entry) => {
    const key = `${entry.label}::${entry.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}
