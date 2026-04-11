import {
  ArrowPathIcon,
  ArrowUturnLeftIcon,
  CheckIcon,
  ClipboardDocumentIcon,
  PencilSquareIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useRef, useState, type MouseEvent } from "react";

import { IconActionMenu } from "@/components/common/IconActionMenu";
import { formatTokenTotal, formatTokenUsage } from "@/lib/format";
import type { MessageRecord, WorkflowSnapshot } from "@/types/chat";

interface ThoughtEntry {
  label: string;
  content: string;
  level?: string;
}

interface MessageCardProps {
  message: MessageRecord;
  workflowMessages: MessageRecord[];
  onDelete: (message: MessageRecord) => void;
  onEdit: (message: MessageRecord, content: string) => void;
  onRegenerate: (message: MessageRecord) => void;
  onRollback: (message: MessageRecord) => void;
}

export function MessageCard({
  message,
  workflowMessages,
  onDelete,
  onEdit,
  onRegenerate,
  onRollback,
}: MessageCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [thoughtsOpen, setThoughtsOpen] = useState(!!message.pending);
  const thoughtsContentRef = useRef<HTMLDivElement>(null);

  const totalTokenLabel = formatTokenTotal(message.token_usage);
  const usageLabel = formatTokenUsage(message.token_usage);
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isReadOnly = ["plan", "think", "tool"].includes(message.message_type ?? "");
  const canCopy = isAssistant || message.role === "tool";
  const thoughtEntries = buildThoughtEntries(message, workflowMessages);

  useEffect(() => {
    if (message.pending) {
      setThoughtsOpen(true);
    }
  }, [message.pending]);

  useEffect(() => {
    if (thoughtsOpen && thoughtsContentRef.current) {
      const el = thoughtsContentRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [message.pending, message.workflow, thoughtEntries, thoughtsOpen]);

  useEffect(() => {
    if (!editing) {
      setDraft(message.content);
    }
  }, [editing, message.content]);

  function stopEvent(event: MouseEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {}
  }

  function submitEdit() {
    const nextContent = draft.trim();
    if (!nextContent || nextContent === message.content) {
      setEditing(false);
      setDraft(message.content);
      return;
    }

    onEdit(message, nextContent);
    setEditing(false);
  }

  const editButtons = editing ? (
    <>
      <button
        aria-label="Save message"
        className="message-action__button message-action__button--editing"
        onClick={(event) => {
          stopEvent(event);
          submitEdit();
        }}
        type="button"
      >
        <CheckIcon />
      </button>
      <button
        aria-label="Cancel edit"
        className="message-action__button message-action__button--editing"
        onClick={(event) => {
          stopEvent(event);
          setEditing(false);
          setDraft(message.content);
        }}
        type="button"
      >
        <XMarkIcon />
      </button>
    </>
  ) : null;

  const menuTrigger = !editing ? (
    <IconActionMenu
      items={[
        ...(canCopy
          ? [
              {
                key: "copy",
                label: "Copy message",
                icon: ClipboardDocumentIcon,
                onSelect: () => {
                  void handleCopy();
                },
              },
            ]
          : []),
        ...(!isReadOnly
          ? [
              {
                key: "edit",
                label: "Edit message",
                icon: PencilSquareIcon,
                onSelect: () => {
                  setEditing(true);
                  setDraft(message.content);
                },
              },
            ]
          : []),
        ...(!isReadOnly && isAssistant
          ? [
              {
                key: "regenerate",
                label: "Regenerate message",
                icon: ArrowPathIcon,
                onSelect: () => {
                  onRegenerate(message);
                },
              },
            ]
          : []),
        ...(!isReadOnly && isUser
          ? [
              {
                key: "rollback",
                label: "Rollback session",
                icon: ArrowUturnLeftIcon,
                onSelect: () => {
                  onRollback(message);
                },
              },
            ]
          : []),
        ...(!isReadOnly
          ? [
              {
                key: "delete",
                label: "Delete message",
                icon: TrashIcon,
                danger: true,
                onSelect: () => {
                  onDelete(message);
                },
              },
            ]
          : []),
      ]}
      triggerClassName="message-action__button message-action__button--subtle"
      triggerLabel="Message actions"
    />
  ) : null;

  return (
    <article className={`message-row message-row--${message.role}${message.pending ? " message-row--pending" : ""}`}>
      <div className={`message-card message-card--${message.role}${message.pending ? " message-card--pending" : ""}`}>
        {thoughtEntries.length > 0 ? (
          <details
            className="message-thoughts"
            open={thoughtsOpen}
            onToggle={(event) => setThoughtsOpen(event.currentTarget.open)}
          >
            <summary className="message-thoughts__summary">
              <SparklesIcon className="message-thoughts__icon" /> Thoughts
            </summary>
            <div className="message-thoughts__content" ref={thoughtsContentRef}>
              {thoughtEntries.map((entry, index) => (
                <div key={`${entry.label}-${index}`} className="message-thoughts__log" data-level={entry.level}>
                  <span className="message-thoughts__log-node">[{entry.label}]</span>
                  <span className="message-thoughts__log-text">{entry.content}</span>
                </div>
              ))}
            </div>
          </details>
        ) : null}

        <div
          className={`message-card__body ${editing ? "message-card__body--editing" : ""}`}
          contentEditable={editing}
          suppressContentEditableWarning
          onInput={(event) => {
            setDraft(event.currentTarget.innerText || "");
          }}
          onKeyDown={(event) => {
            if (!editing) return;
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              submitEdit();
              return;
            }
            if (event.key === "Escape") {
              event.preventDefault();
              event.currentTarget.innerText = message.content;
              setEditing(false);
              setDraft(message.content);
            }
          }}
          ref={(el) => {
            if (editing && el && document.activeElement !== el) {
              el.focus();
              try {
                const range = document.createRange();
                const selection = window.getSelection();
                range.selectNodeContents(el);
                range.collapse(false);
                selection?.removeAllRanges();
                selection?.addRange(range);
              } catch {}
            }
          }}
          style={{
            outline: "none",
            cursor: editing ? "text" : "inherit",
            whiteSpace: "pre-wrap",
            padding: editing ? "0" : undefined,
            margin: editing ? "0" : undefined,
          }}
        >
          {message.content}
        </div>

        {totalTokenLabel || !message.pending ? (
          <div className="message-card__footer">
            {totalTokenLabel ? (
              <span className="message-card__usage" title={usageLabel || totalTokenLabel}>
                {totalTokenLabel}
              </span>
            ) : (
              <span />
            )}

            {!message.pending ? (
              !isUser || editing ? <div className="message-actions message-actions--footer">{editButtons ?? menuTrigger}</div> : null
            ) : null}
          </div>
        ) : null}
      </div>

      {!message.pending && isUser && !editing ? <div className="message-actions message-actions--outside">{menuTrigger}</div> : null}
    </article>
  );
}

function buildThoughtEntries(message: MessageRecord, workflowMessages: MessageRecord[]): ThoughtEntry[] {
  if (message.pending) {
    return workflowMessages.length > 0 ? buildWorkflowMessageThoughtEntries(workflowMessages) : buildLiveThoughtEntries(message.workflow);
  }
  if (message.role !== "assistant" || message.message_type !== "answer") {
    return [];
  }
  return buildWorkflowMessageThoughtEntries(workflowMessages);
}

function buildWorkflowMessageThoughtEntries(workflowMessages: MessageRecord[]): ThoughtEntry[] {
  return workflowMessages.flatMap((entry) => {
    if (entry.message_type === "tool") {
      const toolBlock = extractWorkflowBlock(entry.content, "tool");
      return toolBlock
        ? [{ label: entry.tool_name || "tool", content: toolBlock }]
        : [];
    }
    if (entry.message_type === "plan" || entry.message_type === "think") {
      const reasoningBlock = extractWorkflowBlock(entry.content, entry.message_type);
      return reasoningBlock
        ? [{ label: entry.message_type, content: reasoningBlock }]
        : [];
    }
    return [];
  });
}

function buildLiveThoughtEntries(workflow: WorkflowSnapshot | null | undefined): ThoughtEntry[] {
  if (!workflow) {
    return [];
  }
  return [
    ...workflow.errors.map((error) => ({ label: "error", content: error, level: "error" })),
  ];
}

function extractWorkflowBlock(content: string, target: string): string {
  const sections = parseWorkflowSections(content);
  return sections[target]?.trim() ?? "";
}

function parseWorkflowSections(content: string): Record<string, string> {
  const sections: Record<string, string[]> = {};
  let current: string | null = null;

  for (const line of content.split(/\r?\n/)) {
    const match = line.trim().match(/^\[([a-z_]+)\]$/i);
    if (match) {
      current = match[1].toLowerCase();
      sections[current] = [];
      continue;
    }
    if (current) {
      sections[current].push(line);
    }
  }

  return Object.fromEntries(Object.entries(sections).map(([key, value]) => [key, value.join("\n").trim()]));
}
