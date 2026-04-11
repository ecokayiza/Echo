import { CheckCircleIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import type { WorkflowNodeStatus } from "@/types/chat";
import classes from "./WorkflowGraph.module.css";

interface WorkflowGraphProps {
  nodes: WorkflowNodeStatus[];
  activeNode: string | null;
  toolName?: string | null;
}

export function WorkflowGraph({ nodes, activeNode, toolName }: WorkflowGraphProps) {
  const getStatus = (id: string) => {
    const node = nodes.find((item) => item.node.toLowerCase() === id.toLowerCase());
    if (!node) return "pending";
    if (activeNode?.toLowerCase() === id.toLowerCase()) return "running";
    if (node.status === "success" || node.status === "completed") return "success";
    if (node.status === "skipped" || node.status === "queued") return "pending";
    return node.status;
  };

  const planStatus = getStatus("plan");
  const retrieveStatus = getStatus("retrieve");
  const toolStatus = getStatus("tool");
  const thinkStatus = getStatus("think");
  const answerStatus = getStatus("answer");
  const toolLabel = toolName?.trim() || "</>";

  const NodeItem = ({ title, status, className }: { title: string, status: string, className: string }) => {
    const isSuccess = status === "success";
    const isRunning = status === "running";

    return (
      <div className={`${classes.node} ${classes[`node_${status}`]} ${className}`}>
        {isRunning ? (
          <ArrowPathIcon className={classes.spinner} />
        ) : isSuccess ? (
          <CheckCircleIcon className={classes.iconSuccess} />
        ) : (
          <div className={classes.dotPending} />
        )}
        <span>{title}</span>
      </div>
    );
  };

  return (
    <div className={classes.container}>
      <div className={classes.graphWrapper}>
        <svg className={classes.svgLines} viewBox="0 0 320 280" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#9ca3af" />
            </marker>
          </defs>

          <line x1="100" y1="60" x2="220" y2="60" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="60" y1="100" x2="60" y2="180" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="232" y1="92" x2="188" y2="118" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="188" y1="162" x2="232" y2="188" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="260" y1="180" x2="260" y2="100" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          <line x1="220" y1="220" x2="100" y2="220" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
        </svg>

        <NodeItem title="Plan" status={planStatus} className={classes.posTopLeft} />
        <NodeItem title="Retrieve" status={retrieveStatus} className={classes.posTopRight} />
        <NodeItem title={toolLabel} status={toolStatus} className={classes.posCenter} />
        <NodeItem title="Think" status={thinkStatus} className={classes.posBottomRight} />
        <NodeItem title="Answer" status={answerStatus} className={classes.posBottomLeft} />
      </div>
    </div>
  );
}
