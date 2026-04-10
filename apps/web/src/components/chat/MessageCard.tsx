import {
  ArrowPathIcon,
  ArrowUturnLeftIcon,
  CheckIcon,
  ClipboardDocumentIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useRef, useState, type MouseEvent } from "react";

import { IconActionMenu } from "@/components/common/IconActionMenu";
import { formatTokenTotal, formatTokenUsage } from "@/lib/format";
import type { MessageRecord } from "@/types/chat";

interface MessageCardProps {
  message: MessageRecord;
  onDelete: (message: MessageRecord) => void;
  onEdit: (message: MessageRecord, content: string) => void;
  onRegenerate: (message: MessageRecord) => void;
  onRollback: (message: MessageRecord) => void;
}

export function MessageCard({
  message,
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
  const canCopy = isAssistant;

  useEffect(() => {
    if (message.pending) {
      setThoughtsOpen(true);
    }
  }, [message.pending]);

  useEffect(() => {
    if (message.pending && thoughtsOpen && thoughtsContentRef.current) {
      const el = thoughtsContentRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [message.workflow?.logs, message.pending, thoughtsOpen]);

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
        {
          key: "edit",
          label: "Edit message",
          icon: PencilSquareIcon,
          onSelect: () => {
            setEditing(true);
            setDraft(message.content);
          },
        },
        ...(isAssistant
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
        ...(isUser
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
        {
          key: "delete",
          label: "Delete message",
          icon: TrashIcon,
          danger: true,
          onSelect: () => {
            onDelete(message);
          },
        },
      ]}
      triggerClassName="message-action__button message-action__button--subtle"
      triggerLabel="Message actions"
    />
  ) : null;

  const visibleLogs = message.workflow?.logs?.filter(log => {
    if (log.level === "error") return true;
    const msg = log.message;
    if (msg === "Workflow created.") return false;
    if (/^[a-zA-Z_]+ started\.$/.test(msg)) return false;
    if (/^[A-Za-z_]+ selected '[^']+'\.$/.test(msg)) return false;
    if (msg === "Skill catalog injected for retrieve.") return false;
    if (msg.startsWith("This route answered without")) return false;
    return true;
  }) || [];

  return (
    <article className={`message-row message-row--${message.role}${message.pending ? " message-row--pending" : ""}`}>
      <div className={`message-card message-card--${message.role}${message.pending ? " message-card--pending" : ""}`}>
        
        {visibleLogs.length > 0 && (
          <details
            className="message-thoughts"
            open={thoughtsOpen}
            onToggle={(e) => setThoughtsOpen(e.currentTarget.open)}
          >
            <summary className="message-thoughts__summary">
              <SparklesIcon className="message-thoughts__icon" /> Thoughts
            </summary>
            <div className="message-thoughts__content" ref={thoughtsContentRef}>
              {visibleLogs.map((log, i) => (
                <div key={i} className="message-thoughts__log" data-level={log.level}>
                  {log.node ? <span className="message-thoughts__log-node">[{log.node}]</span> : null}
                  <span className="message-thoughts__log-text">{log.message}</span>
                </div>
              ))}
            </div>
          </details>
        )}

        <div
          className={`message-card__body ${editing ? "message-card__body--editing" : ""}`}
          contentEditable={editing}
          suppressContentEditableWarning
          onInput={(e) => {
            setDraft(e.currentTarget.innerText || "");
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
                const sel = window.getSelection();
                range.selectNodeContents(el);
                range.collapse(false);
                sel?.removeAllRanges();
                sel?.addRange(range);
              } catch (e) {}
            }
          }}
          style={{ 
            outline: "none", 
            cursor: editing ? "text" : "inherit", 
            whiteSpace: "pre-wrap",
            padding: editing ? "0" : undefined,
            margin: editing ? "0" : undefined
          }}
        >
          {message.content}
        </div>

        {totalTokenLabel || !message.pending ? (
          <div className="message-card__footer">
            {totalTokenLabel ? (
              <span
                className="message-card__usage"
                title={usageLabel || totalTokenLabel}
              >
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

      {!message.pending && isUser && !editing ? (
        <div className="message-actions message-actions--outside">
          {menuTrigger}
        </div>
      ) : null}
    </article>
  );
}
