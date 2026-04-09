import {
  ArrowPathIcon,
  ArrowUturnLeftIcon,
  CheckIcon,
  ClipboardDocumentIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState, type KeyboardEvent, type MouseEvent } from "react";

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
  const totalTokenLabel = formatTokenTotal(message.token_usage);
  const usageLabel = formatTokenUsage(message.token_usage);
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const canCopy = isAssistant;

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

  function onEditorKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submitEdit();
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setEditing(false);
      setDraft(message.content);
    }
  }

  const actionButtons = editing ? (
    <>
      <button
        aria-label="Save message"
        className="message-action__button"
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
        className="message-action__button"
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
  ) : (
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
  );

  return (
    <article className={`message-row message-row--${message.role}${message.pending ? " message-row--pending" : ""}`}>
      <div className={`message-card message-card--${message.role}${message.pending ? " message-card--pending" : ""}`}>
        {editing ? (
          <div className="message-inline-editor">
            <textarea
              autoFocus
              className="message-inline-editor__input"
              onChange={(event) => {
                setDraft(event.target.value);
              }}
              onKeyDown={onEditorKeyDown}
              rows={Math.max(3, Math.min(8, draft.split("\n").length + 1))}
              value={draft}
            />
          </div>
        ) : (
          <div className="message-card__body">{message.content}</div>
        )}

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
              <div className={`message-actions${isUser ? " message-actions--side" : " message-actions--footer"}`}>
                {actionButtons}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}
