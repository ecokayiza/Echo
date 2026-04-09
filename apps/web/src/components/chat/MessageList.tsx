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

  useEffect(() => {
    const node = listRef.current;
    if (!node) {
      return;
    }

    node.scrollTop = node.scrollHeight;
  }, [messages]);

  return (
    <section className="message-list" aria-live="polite" ref={listRef}>
      {messages.length === 0 ? (
        <EmptyState
          description={ready ? "Ask a question to create the first meaningful exchange in this session." : "Connecting to the backend and restoring the selected thread."}
          title={ready ? "Start A Conversation" : "Loading Workspace"}
        />
      ) : (
        messages.map((message) => (
          <MessageCard
            key={message.id}
            message={message}
            onDelete={onDelete}
            onEdit={onEdit}
            onRegenerate={onRegenerate}
            onRollback={onRollback}
          />
        ))
      )}
    </section>
  );
}
