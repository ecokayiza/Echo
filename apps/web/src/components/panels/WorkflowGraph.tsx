import { CheckCircleIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import type { WorkflowNodeStatus } from "@/types/chat";
import classes from "./WorkflowGraph.module.css";

interface WorkflowGraphProps {
  nodes: WorkflowNodeStatus[];
  activeNode: string | null;
}

export function WorkflowGraph({ nodes, activeNode }: WorkflowGraphProps) {
  // Extract node status safely
  const getStatus = (id: string) => {
    const node = nodes.find(n => n.node.toLowerCase().includes(id.toLowerCase()));
    if (!node) return "pending";
    if (activeNode?.toLowerCase().includes(id.toLowerCase())) return "running";
    if (node.status === "success" || node.status === "completed") return "success";
    return node.status; // fallback
  };

  const planStatus = getStatus("plan");
  const retrieveStatus = getStatus("retrieve");
  const thinkStatus = getStatus("think");
  const answerStatus = getStatus("answer");

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
        <svg className={classes.svgLines} viewBox="0 0 280 280" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 1 L 8 5 L 0 9 z" fill="#9ca3af" />
            </marker>
          </defs>

          {/* Plan to Retrieve (Right) */}
          <line x1="85" y1="40" x2="195" y2="40" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          
          {/* Plan to Answer (Down) */}
          <line x1="40" y1="85" x2="40" y2="195" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          
          {/* Retrieve to Think (Down) - shifted slightly left */}
          <line x1="230" y1="85" x2="230" y2="195" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          
          {/* Think to Retrieve (Up) - shifted slightly right */}
          <line x1="250" y1="195" x2="250" y2="85" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
          
          {/* Think to Answer (Left) */}
          <line x1="195" y1="240" x2="85" y2="240" stroke="#9ca3af" strokeWidth="1.5" markerEnd="url(#arrow)" />
        </svg>

        <NodeItem title="Plan" status={planStatus} className={classes.posTopLeft} />
        <NodeItem title="Retrieve" status={retrieveStatus} className={classes.posTopRight} />
        <NodeItem title="Think" status={thinkStatus} className={classes.posBottomRight} />
        <NodeItem title="Answer" status={answerStatus} className={classes.posBottomLeft} />
      </div>
    </div>
  );
}
