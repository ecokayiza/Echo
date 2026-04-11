import {
  CheckIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState } from "react";

import { Button, Modal } from "@/components/common";
import { Field } from "@/components/common/Field";
import { IconActionMenu } from "@/components/common/IconActionMenu";
import { formatNumber } from "@/lib/format";
import type { DatabaseRecord } from "@/types/chat";

interface DatabaseSettingsModalProps {
  activeDatabaseId: string | null;
  busy: boolean;
  databases: DatabaseRecord[];
  embeddingModelNames: string[];
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, embeddingModelName: string) => void;
  onDelete: (database: DatabaseRecord) => void;
  onRename: (database: DatabaseRecord, name: string) => void;
  onSelect: (databaseId: string) => void;
}

export function DatabaseSettingsModal({
  activeDatabaseId,
  busy,
  databases,
  embeddingModelNames,
  open,
  onClose,
  onCreate,
  onDelete,
  onRename,
  onSelect,
}: DatabaseSettingsModalProps) {
  const [nameDraft, setNameDraft] = useState("");
  const [embeddingModelName, setEmbeddingModelName] = useState(embeddingModelNames[0] ?? "");
  const [editingDatabaseId, setEditingDatabaseId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  useEffect(() => {
    if (!open) {
      setNameDraft("");
      setEditingDatabaseId(null);
      setRenameDraft("");
    }
  }, [open]);

  useEffect(() => {
    if (!embeddingModelNames.includes(embeddingModelName)) {
      setEmbeddingModelName(embeddingModelNames[0] ?? "");
    }
  }, [embeddingModelName, embeddingModelNames]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Database Settings"
      description="Manage database selection and paired embedding models. Content management will land here next."
      footer={
        <Button onClick={onClose} variant="ghost">
          Close
        </Button>
      }
    >
      <div className="database-settings-grid">
        <Field htmlFor="database-create-name" label="New Database">
          <input
            disabled={busy}
            id="database-create-name"
            onChange={(event) => {
              setNameDraft(event.target.value);
            }}
            placeholder="Research Notes"
            type="text"
            value={nameDraft}
          />
        </Field>

        <Field htmlFor="database-embedding-model" label="Paired Embedding Model">
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

        <Button
          disabled={busy || !nameDraft.trim() || !embeddingModelName}
          onClick={() => {
            onCreate(nameDraft, embeddingModelName);
            setNameDraft("");
          }}
          variant="primary"
        >
          Create Database
        </Button>
      </div>

      <ul className="database-list database-list--modal">
        {databases.map((database) => {
          const isActive = database.id === activeDatabaseId;
          const isEditing = database.id === editingDatabaseId;

          return (
            <li key={database.id} className="database-list__item">
              <div className={`database-card database-card--modal${isActive ? " database-card--active" : ""}`}>
                <div className="database-card__row">
                  {isEditing ? (
                    <input
                      autoFocus
                      className="session-card__input"
                      onChange={(event) => {
                        setRenameDraft(event.target.value);
                      }}
                      type="text"
                      value={renameDraft}
                    />
                  ) : (
                    <strong className="database-card__title">{database.name}</strong>
                  )}

                  <div className="session-actions">
                    {isEditing ? (
                      <>
                        <button
                          aria-label="Save database name"
                          className="session-action__button"
                          onClick={() => {
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
                          className="session-action__button"
                          onClick={() => {
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
                        triggerClassName="session-action__button session-action__button--subtle"
                        triggerLabel="Database actions"
                      />
                    )}
                  </div>
                </div>

                <p className="database-card__meta">{database.embedding_model_name}</p>
                <div className="database-card__row">
                  <span className="database-card__count">{formatNumber(database.document_count)} docs</span>
                  <Button
                    disabled={busy || isActive}
                    onClick={() => {
                      onSelect(database.id);
                    }}
                    variant={isActive ? "ghost" : "secondary"}
                  >
                    {isActive ? "Selected" : "Select"}
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
