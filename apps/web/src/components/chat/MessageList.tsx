import { useEffect, useRef } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import type { MessageRecord } from "@/types/chat";

import { MessageCard } from "./MessageCard";

interface MessageListProps {
  ready: boolean;
  messages: MessageRecord[];
  onDelete: (message: MessageRecord) => void;
  onEdit: (message: MessageRecord, content: string) => void;
  onRegenerate: (message: MessageRecord) => void;
  onRollback: (message: MessageRecord) => void;
}

export function MessageList({
  messages,
  onDelete,
  onEdit,
  onRegenerate,
  onRollback,
  ready,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const workflowMessagesByTurn = new Map<string, MessageRecord[]>();
  const visibleMessages: MessageRecord[] = [];

  for (const message of messages) {
    if (["plan", "think", "tool"].includes(message.message_type ?? "") && message.workflow_turn_id) {
      const items = workflowMessagesByTurn.get(message.workflow_turn_id) ?? [];
      items.push(message);
      workflowMessagesByTurn.set(message.workflow_turn_id, items);
      continue;
    }
    visibleMessages.push(message);
  }

  useEffect(() => {
    const node = listRef.current;
    if (!node) {
      return;
    }

    node.scrollTop = node.scrollHeight;
  }, [messages]);

  return (
    <section className="message-list" aria-live="polite" ref={listRef}>
      {visibleMessages.length === 0 ? (
        <EmptyState
          description={ready ? "Ask a question to create the first meaningful exchange in this session." : "Connecting to the backend and restoring the selected thread."}
          title={ready ? "Start A Conversation" : "Loading Workspace"}
        />
      ) : (
        visibleMessages.map((message) => (
          <MessageCard
            key={message.id}
            message={message}
            onDelete={onDelete}
            onEdit={onEdit}
            onRegenerate={onRegenerate}
            onRollback={onRollback}
            workflowMessages={message.workflow_turn_id ? workflowMessagesByTurn.get(message.workflow_turn_id) ?? [] : []}
          />
        ))
      )}
    </section>
  );
}
