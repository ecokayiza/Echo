import { SectionCard } from "@/components/common/SectionCard";
import type { WorkflowSnapshot } from "@/types/chat";
import { WorkflowGraph } from "./WorkflowGraph";

interface WorkflowPanelProps {
  workflow: WorkflowSnapshot | null;
}

export function WorkflowPanel({ workflow }: WorkflowPanelProps) {
  const logEntries = workflow ? buildWorkflowLogEntries(workflow) : [];
  const roundCount = workflow?.retrieve_round ?? 0;

  return (
    <SectionCard
      actions={workflow ? <span className="workflow-round-pill">Round {roundCount}</span> : null}
      className="section-card--fill"
      eyebrow="Workflow"
    >
      <div aria-label="Workflow modern graph" className="workflow-panel__graph-wrap">
        <WorkflowGraph
          nodes={workflow?.node_statuses ?? []}
          activeNode={workflow?.active_node || null}
          toolName={workflow?.tool_name || null}
        />
      </div>

      {workflow && logEntries.length > 0 ? (
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
    </SectionCard>
  );
}

function buildWorkflowLogEntries(workflow: WorkflowSnapshot) {
  const errorMessages = new Set(workflow.errors.map((error) => formatWorkflowLogMessage(error)));
  const stepEntries = workflow.node_statuses
    .filter((node) => node.detail)
    .map((node) => ({
      label: node.node,
      message: formatWorkflowLogMessage(node.detail),
    }));

  const errorEntries = workflow.errors.map((error) => ({
    label: "error",
    message: formatWorkflowLogMessage(error),
  }));

  const extraEntries = workflow.logs
    .filter((entry) => entry.message)
    .map((entry) => ({
      label: entry.node || entry.level || "log",
      message: formatWorkflowLogMessage(entry.message),
    }))
    .filter((entry) => !errorMessages.has(entry.message));

  const seen = new Set<string>();
  return [...stepEntries, ...errorEntries, ...extraEntries].filter((entry) => {
    if (!entry.message) {
      return false;
    }
    const key = `${entry.label}::${entry.message}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatWorkflowLogMessage(value: unknown) {
  const rawOutputStart = "LLM raw output:";
  const maxLength = 220;
  const text = String(value ?? "").trim();
  const rawIndex = text.indexOf(rawOutputStart);
  const summary = rawIndex >= 0 ? text.slice(0, rawIndex).trim() : text;
  if (summary.length <= maxLength) {
    return summary;
  }
  return `${summary.slice(0, maxLength).trimEnd()}...`;
}
