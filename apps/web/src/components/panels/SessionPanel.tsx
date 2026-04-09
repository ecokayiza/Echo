import {
  CheckIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState, type KeyboardEvent, type MouseEvent } from "react";

import { Button } from "@/components/common/Button";
import { EmptyState } from "@/components/common/EmptyState";
import { IconActionMenu } from "@/components/common/IconActionMenu";
import { SectionCard } from "@/components/common/SectionCard";
import { formatNumber } from "@/lib/format";
import type { SessionSummary } from "@/types/chat";

interface SessionPanelProps {
  busy: boolean;
  ready: boolean;
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onCreate: () => void;
  onDelete: (session: SessionSummary) => void;
  onRename: (session: SessionSummary, title: string) => void;
  onSelect: (sessionId: string) => void;
}

export function SessionPanel({
  activeSessionId,
  busy,
  onCreate,
  onDelete,
  onRename,
  onSelect,
  ready,
  sessions,
}: SessionPanelProps) {
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");

  useEffect(() => {
    if (!editingSessionId) {
      setTitleDraft("");
    }
  }, [editingSessionId]);

  function stopEvent(event: MouseEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
  }

  function startEditing(session: SessionSummary, event: MouseEvent<HTMLButtonElement>) {
    stopEvent(event);
    setEditingSessionId(session.session_id);
    setTitleDraft(session.title);
  }

  function cancelEditing(event?: MouseEvent<HTMLElement>) {
    event?.preventDefault();
    event?.stopPropagation();
    setEditingSessionId(null);
    setTitleDraft("");
  }

  function submitEditing(session: SessionSummary) {
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === session.title) {
      setEditingSessionId(null);
      setTitleDraft("");
      return;
    }

    onRename(session, nextTitle);
    setEditingSessionId(null);
    setTitleDraft("");
  }

  function onEditorKeyDown(session: SessionSummary, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      submitEditing(session);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      cancelEditing();
    }
  }

  return (
    <SectionCard
      bodyClassName="section-card__body--fill"
      className="section-card--fill"
      eyebrow="Eco_RAG"
      title="Sessions"
      actions={
        <Button disabled={busy} onClick={onCreate} variant="primary">
          New
        </Button>
      }
    >
      {sessions.length === 0 ? (
        <EmptyState
          compact
          description={ready ? "Create the first conversation to start working with the workflow." : "Loading saved conversations from disk."}
          title={ready ? "No Sessions Yet" : "Loading Sessions"}
        />
      ) : (
        <ul className="session-list">
          {sessions.map((session) => {
            const isActive = session.session_id === activeSessionId;
            const isEditing = editingSessionId === session.session_id;

            return (
              <li key={session.session_id} className="session-list__item">
                <div className={`session-item${isActive ? " session-item--active" : ""}`}>
                  <button
                    aria-pressed={isActive}
                    className={`session-card${isActive ? " session-card--active" : ""}`}
                    disabled={busy}
                    onClick={() => {
                      if (!isEditing) {
                        onSelect(session.session_id);
                      }
                    }}
                    type="button"
                  >
                    <div className="session-card__row">
                      {isEditing ? (
                        <input
                          autoFocus
                          className="session-card__input"
                          onChange={(event) => {
                            setTitleDraft(event.target.value);
                          }}
                          onClick={(event) => {
                            stopEvent(event);
                          }}
                          onKeyDown={(event) => {
                            onEditorKeyDown(session, event);
                          }}
                          type="text"
                          value={titleDraft}
                        />
                      ) : (
                        <strong className="session-card__title">{session.title}</strong>
                      )}

                      <div className="session-actions">
                        {isEditing ? (
                          <>
                            <button
                              aria-label="Save session title"
                              className="session-action__button"
                              onClick={(event) => {
                                stopEvent(event);
                                submitEditing(session);
                              }}
                              type="button"
                            >
                              <CheckIcon />
                            </button>
                            <button
                              aria-label="Cancel rename"
                              className="session-action__button"
                              onClick={(event) => {
                                cancelEditing(event);
                              }}
                              type="button"
                            >
                              <XMarkIcon />
                            </button>
                          </>
                        ) : (
                          <IconActionMenu
                            disabled={busy}
                            items={[
                              {
                                key: "rename",
                                label: "Rename session",
                                icon: PencilSquareIcon,
                                onSelect: () => {
                                  setEditingSessionId(session.session_id);
                                  setTitleDraft(session.title);
                                },
                              },
                              {
                                key: "delete",
                                label: "Delete session",
                                icon: TrashIcon,
                                danger: true,
                                onSelect: () => {
                                  onDelete(session);
                                },
                              },
                            ]}
                            triggerClassName="session-action__button session-action__button--subtle"
                            triggerLabel="Session actions"
                          />
                        )}
                      </div>
                    </div>
                    <p className="session-card__preview">{session.preview || "No messages yet."}</p>
                    <div className="session-card__meta">
                      <span>{formatNumber(session.message_count)} msgs</span>
                      <span>{formatNumber(session.total_tokens)} tokens</span>
                    </div>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
