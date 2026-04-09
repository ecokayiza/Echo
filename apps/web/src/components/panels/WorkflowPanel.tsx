import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import { formatNumber } from "@/lib/format";
import type { WorkflowNodeStatus, WorkflowSnapshot } from "@/types/chat";

interface WorkflowPanelProps {
  workflow: WorkflowSnapshot | null;
}

export function WorkflowPanel({ workflow }: WorkflowPanelProps) {
  return (
    <SectionCard
      eyebrow="Trace"
      title="Workflow Trace"
    >
      {!workflow ? (
        <EmptyState compact description="发送一条消息后，这里会显示 workflow 运行轨迹。" title="Trace Idle" />
      ) : (
        <>
          <div className="trace-summary">
            <div className="trace-summary__item">
              <span>Status</span>
              <strong>{workflow.status}</strong>
            </div>
            <div className="trace-summary__item">
              <span>Active</span>
              <strong>{workflow.active_node ?? "none"}</strong>
            </div>
            <div className="trace-summary__item">
              <span>Context</span>
              <strong>{formatNumber(workflow.context_items.length)}</strong>
            </div>
          </div>

          <div className="trace-graph" aria-label="Workflow graph">
            {workflow.node_statuses.map((node: WorkflowNodeStatus, index, list) => {
              const isLast = index === list.length - 1;
              return (
                <div className="trace-node" key={node.node}>
                  <div className="trace-node__rail" aria-hidden="true">
                    <span className={`trace-node__dot trace-node__dot--${node.status}`} />
                    {!isLast ? <span className="trace-node__line" /> : null}
                  </div>
                  <article className={`trace-node__card trace-node__card--${node.status}`}>
                    <div className="trace-node__header">
                      <strong>{node.node}</strong>
                      <span>{node.status}</span>
                    </div>
                    <p className="trace-node__detail">{node.detail}</p>
                  </article>
                </div>
              );
            })}
          </div>

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
