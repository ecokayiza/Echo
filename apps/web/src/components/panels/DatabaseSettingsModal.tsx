import {
  CheckIcon,
  PencilSquareIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState, type KeyboardEvent } from "react";

import { Button, Modal } from "@/components/common";
import { Field } from "@/components/common/Field";
import { IconActionMenu } from "@/components/common/IconActionMenu";
import { formatNumber } from "@/lib/format";
import type { DatabaseRecord } from "@/types/chat";

interface DatabaseSettingsModalProps {
  activeDatabaseId: string | null;
  busy: boolean;
  databases: DatabaseRecord[];
  defaultBackend: DatabaseRecord["backend"];
  embeddingModelNames: string[];
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, embeddingModelName: string, backend: DatabaseRecord["backend"]) => void;
  onDelete: (database: DatabaseRecord) => void;
  onRename: (database: DatabaseRecord, name: string) => void;
  onSelect: (databaseId: string) => void;
}

const EMOJIS = ["🔍", "💎", "🧠", "⭐", "🔗", "🔄", "📈", "🧩", "🎯", "🚀", "💡", "🎨"];

export function DatabaseSettingsModal({
  activeDatabaseId,
  busy,
  databases,
  defaultBackend,
  embeddingModelNames,
  open,
  onClose,
  onCreate,
  onDelete,
  onRename,
  onSelect,
}: DatabaseSettingsModalProps) {
  const [nameDraft, setNameDraft] = useState("");
  const [backend, setBackend] = useState<DatabaseRecord["backend"]>(defaultBackend);
  const [embeddingModelName, setEmbeddingModelName] = useState(embeddingModelNames[0] ?? "");
  const [editingDatabaseId, setEditingDatabaseId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    if (!open) {
      setNameDraft("");
      setEditingDatabaseId(null);
      setRenameDraft("");
      setIsCreating(false);
      setBackend(defaultBackend);
    }
  }, [defaultBackend, open]);

  useEffect(() => {
    if (!isCreating) {
      setBackend(defaultBackend);
    }
  }, [defaultBackend, isCreating]);

  useEffect(() => {
    if (!embeddingModelNames.includes(embeddingModelName)) {
      setEmbeddingModelName(embeddingModelNames[0] ?? "");
    }
  }, [embeddingModelName, embeddingModelNames]);

  function createDatabase() {
    const nextName = nameDraft.trim();
    if (!nextName || !embeddingModelName) {
      return;
    }
    onCreate(nextName, embeddingModelName, backend);
    setNameDraft("");
    setBackend(defaultBackend);
  }

  function onRenameKeyDown(database: DatabaseRecord, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onRename(database, renameDraft);
      setEditingDatabaseId(null);
      setRenameDraft("");
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setEditingDatabaseId(null);
      setRenameDraft("");
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        panelClassName="modal__panel--wide database-settings-modal"
        title="Databases"
        description="Select, create, rename, and remove vector databases."
        footer={
          <Button onClick={onClose} variant="ghost">
            Close
          </Button>
        }
      >
        <div className="database-settings-card-grid">
          <section 
            className="database-settings-tile database-settings-tile--create database-settings-tile--selectable database-settings-create-card"
            aria-label="Create database"
            onClick={() => {
              setIsCreating(true);
            }}
          >
            <div aria-hidden="true" className="database-settings-tile__create-icon">
              <PlusIcon />
            </div>
            <strong className="database-settings-tile__title database-settings-tile__create-title">新建笔记本</strong>
          </section>

          {databases.map((database, index) => {
          const isActive = database.id === activeDatabaseId;
          const isEditing = database.id === editingDatabaseId;
          const canSelect = !busy && !isEditing && !isActive;

          return (
            <article
              key={database.id}
              aria-current={isActive ? "true" : undefined}
              className={`database-settings-tile database-settings-tile--palette-${index % 4}${
                isActive ? " database-settings-tile--active" : ""
              }${canSelect ? " database-settings-tile--selectable" : ""}`}
              onClick={() => {
                if (canSelect) {
                  onSelect(database.id);
                }
              }}
            >
              {!isEditing ? (
                <button
                  aria-label={isActive ? `${database.name} is selected` : `Select ${database.name}`}
                  aria-pressed={isActive}
                  className="database-settings-tile__select"
                  disabled={busy || isActive}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(database.id);
                  }}
                  type="button"
                />
              ) : null}

              <div className="database-settings-tile__top">
                <span className="database-settings-tile__icon database-settings-tile__icon--emoji" aria-hidden="true">
                  {EMOJIS[index % EMOJIS.length]}
                </span>
                <div className="database-settings-tile__actions">
                  {isEditing ? (
                    <>
                      <button
                        aria-label="Save database name"
                        className="database-settings-tile__action"
                        onClick={(event) => {
                          event.stopPropagation();
                          onRename(database, renameDraft);
                          setEditingDatabaseId(null);
                          setRenameDraft("");
                        }}
                        type="button"
                      >
                        <CheckIcon />
                      </button>
                      <button
                        aria-label="Cancel database rename"
                        className="database-settings-tile__action"
                        onClick={(event) => {
                          event.stopPropagation();
                          setEditingDatabaseId(null);
                          setRenameDraft("");
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
                          label: "Rename database",
                          icon: PencilSquareIcon,
                          onSelect: () => {
                            setEditingDatabaseId(database.id);
                            setRenameDraft(database.name);
                          },
                        },
                        {
                          key: "delete",
                          label: "Delete database",
                          icon: TrashIcon,
                          danger: true,
                          onSelect: () => {
                            onDelete(database);
                          },
                        },
                      ]}
                      triggerClassName="database-settings-tile__menu"
                      triggerLabel={`Actions for ${database.name}`}
                    />
                  )}
                </div>
              </div>

              <div className="database-settings-tile__copy">
                {isEditing ? (
                  <input
                    autoFocus
                    className="database-settings-tile__input"
                    onChange={(event) => {
                      setRenameDraft(event.target.value);
                    }}
                    onClick={(event) => {
                      event.stopPropagation();
                    }}
                    onKeyDown={(event) => {
                      onRenameKeyDown(database, event);
                    }}
                    type="text"
                    value={renameDraft}
                  />
                ) : (
                  <strong className="database-settings-tile__title" title={database.name}>
                    {database.name}
                  </strong>
                )}
                <span className="database-settings-tile__meta">
                  {formatDatabaseDate(database.updated_at || database.created_at)} · {formatNumber(database.document_count)}个来源
                </span>
                <span className="database-settings-tile__model" title={database.embedding_model_name}>
                  {database.embedding_model_name}
                </span>
                <span className="database-settings-tile__model">
                  {formatDatabaseBackend(database.backend)}
                </span>
              </div>
            </article>
          );
        })}
        </div>
      </Modal>

      <Modal
        open={isCreating}
        onClose={() => setIsCreating(false)}
        title="新建笔记本"
        description="Pair it to one embedding model"
        footer={
          <>
            <Button onClick={() => setIsCreating(false)} variant="ghost">
              Cancel
            </Button>
            <Button
              disabled={busy || !nameDraft.trim() || !embeddingModelName}
              onClick={() => {
                createDatabase();
                setIsCreating(false);
              }}
              variant="primary"
            >
              Create
            </Button>
          </>
        }
      >
        <div className="database-create-form">
          <Field htmlFor="database-create-name" label="Name">
            <input
              disabled={busy}
              id="database-create-name"
              autoFocus
              onChange={(event) => {
                setNameDraft(event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  createDatabase();
                  setIsCreating(false);
                }
              }}
              placeholder="Research Notes"
              type="text"
              value={nameDraft}
            />
          </Field>

          <Field htmlFor="database-embedding-model" label="Embedding">
            <select
              disabled={busy || embeddingModelNames.length === 0}
              id="database-embedding-model"
              onChange={(event) => {
                setEmbeddingModelName(event.target.value);
              }}
              value={embeddingModelNames.length > 0 ? embeddingModelName : ""}
            >
              {embeddingModelNames.length > 0 ? (
                embeddingModelNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))
              ) : (
                <option value="">No embedding models configured</option>
              )}
            </select>
          </Field>

          <Field htmlFor="database-create-backend" label="Backend">
            <select
              disabled={busy}
              id="database-create-backend"
              onChange={(event) => {
                setBackend(event.target.value as DatabaseRecord["backend"]);
              }}
              value={backend}
            >
              <option value="chroma">Chroma</option>
              <option value="faiss">FAISS</option>
            </select>
          </Field>
        </div>
      </Modal>
    </>
  );
}

function formatDatabaseDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知时间";
  }
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

function formatDatabaseBackend(backend: DatabaseRecord["backend"]) {
  return backend === "faiss" ? "FAISS" : "Chroma";
}
