import {
  ArrowUpTrayIcon,
  CheckIcon,
  Cog6ToothIcon,
  CpuChipIcon,
  DocumentTextIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/common";
import { IconActionMenu } from "@/components/common/IconActionMenu";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import { formatNumber } from "@/lib/format";
import type { DatabaseDocumentRecord, DatabaseRecord, UploadJobRecord } from "@/types/chat";

interface DatabasePanelProps {
  activeDatabaseId: string | null;
  busy: boolean;
  databases: DatabaseRecord[];
  documents: DatabaseDocumentRecord[];
  uploadJob: UploadJobRecord | null;
  onOpenEmbeddingSettings: () => void;
  onOpenSettings: () => void;
  onDeleteDocument: (document: DatabaseDocumentRecord) => void;
  onRenameDocument: (document: DatabaseDocumentRecord, name: string) => void;
  onUploadFiles: (files: File[]) => void;
  onSelect: (databaseId: string) => void;
}

export function DatabasePanel({
  activeDatabaseId,
  busy,
  databases,
  documents,
  uploadJob,
  onOpenEmbeddingSettings,
  onOpenSettings,
  onDeleteDocument,
  onRenameDocument,
  onUploadFiles,
  onSelect,
}: DatabasePanelProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [editingDocumentId, setEditingDocumentId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const activeDatabase = databases.find((database) => database.id === activeDatabaseId) ?? null;
  const currentUploadDisplay =
    uploadJob?.current_file_name ??
    uploadJob?.files.find((file) => file.status === "processing")?.source_name ??
    uploadJob?.files.find((file) => file.status === "queued")?.source_name ??
    uploadJob?.files[0]?.source_name ??
    uploadJob?.message ??
    null;

  useEffect(() => {
    if (!editingDocumentId) {
      setRenameDraft("");
      return;
    }

    const target = documents.find((document) => document.id === editingDocumentId);
    if (!target) {
      setEditingDocumentId(null);
      setRenameDraft("");
    }
  }, [documents, editingDocumentId]);

  function cancelEditingDocument() {
    setEditingDocumentId(null);
    setRenameDraft("");
  }

  function submitEditingDocument(document: DatabaseDocumentRecord) {
    const nextName = renameDraft.trim();
    if (!nextName || nextName === document.source_name.trim()) {
      cancelEditingDocument();
      return;
    }

    onRenameDocument(document, nextName);
    cancelEditingDocument();
  }

  function onDocumentEditorKeyDown(document: DatabaseDocumentRecord, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      submitEditingDocument(document);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      cancelEditingDocument();
    }
  }

  return (
    <SectionCard
      bodyClassName="section-card__body--fill database-panel__body"
      className="section-card--fill"
      eyebrow="Database"
      actions={
        <div className="section-card__actions">
          <button
            aria-label="Open embedding model settings"
            className="model-settings-button"
            disabled={busy}
            onClick={onOpenEmbeddingSettings}
            type="button"
          >
            <CpuChipIcon />
          </button>
          <button
            aria-label="Open database settings"
            className="model-settings-button"
            disabled={busy}
            onClick={onOpenSettings}
            type="button"
          >
            <Cog6ToothIcon />
          </button>
        </div>
      }
    >
      {databases.length === 0 ? (
        <EmptyState compact title="No Databases" />
      ) : (
        <>
          <ul className="database-list">
            {databases.map((database) => {
              const isActive = database.id === activeDatabaseId;
              return (
                <li key={database.id} className="database-list__item">
                  <button
                    aria-pressed={isActive}
                    className={`database-card${isActive ? " database-card--active" : ""}`}
                    disabled={busy}
                    onClick={() => {
                      onSelect(database.id);
                    }}
                    type="button"
                  >
                    <div className="database-card__row">
                      <strong className="database-card__title" title={database.name}>
                        {database.name}
                      </strong>
                      <span className="database-card__count">{formatNumber(database.document_count)} files</span>
                    </div>
                    <p className="database-card__meta">{database.embedding_model_name}</p>
                  </button>
                </li>
              );
            })}
          </ul>

          <section className="database-documents" aria-label="Database files">
            <div className="database-documents__header">
              <div className="database-documents__copy">
                <strong className="database-documents__title">Docs</strong>
              </div>
              <Button
                disabled={busy || !activeDatabase}
                onClick={() => {
                  uploadInputRef.current?.click();
                }}
                size="sm"
                variant="secondary"
              >
                <ArrowUpTrayIcon />
                Upload
              </Button>
              <input
                ref={uploadInputRef}
                accept=".txt,.md,.pdf"
                className="sr-only"
                multiple
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length > 0) {
                    onUploadFiles(files);
                  }
                  event.target.value = "";
                }}
                type="file"
              />
            </div>

            {uploadJob ? (
              <section
                aria-label="Embedding upload progress"
                className={`upload-progress-card upload-progress-card--${uploadJob.status}`}
              >
                <div className="upload-progress-card__row">
                  <div className="upload-progress-card__copy">
                    <strong className="upload-progress-card__title">
                      Embedding
                    </strong>
                    <span className="upload-progress-card__meta">{currentUploadDisplay}</span>
                  </div>
                  <span className="upload-progress-card__percent">{Math.round(uploadJob.progress)}%</span>
                </div>
                <div
                  aria-valuemax={100}
                  aria-valuemin={0}
                  aria-valuenow={Math.round(uploadJob.progress)}
                  className="upload-progress-card__bar"
                  role="progressbar"
                >
                  <span
                    className="upload-progress-card__fill"
                    style={{ width: `${Math.max(uploadJob.progress > 0 ? 2 : 0, Math.min(100, uploadJob.progress))}%` }}
                  />
                </div>
                {uploadJob.files.length > 0 ? (
                  <ul className="upload-progress-file-list">
                    {uploadJob.files.map((file) => (
                      <li key={file.id} className="upload-progress-file-list__item">
                        <div className="upload-progress-file-list__row">
                          <strong className="upload-progress-file-list__title" title={file.source_name}>
                            {file.source_name}
                          </strong>
                          <span className="upload-progress-file-list__meta">
                            {file.status === "completed"
                              ? "Done"
                              : file.status === "skipped"
                                ? "Skipped"
                              : file.status === "failed"
                                ? "Failed"
                                : file.status === "processing"
                                  ? `${formatNumber(file.embedded_chunks)}/${formatNumber(file.chunk_count)} chunks`
                                  : "Queued"}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ) : null}

            {documents.length > 0 ? (
              <ul className="database-document-list">
                {documents.map((document) => {
                  const isEditing = editingDocumentId === document.id;
                  const metaLabel = `${(document.source_type || "unknown").toUpperCase()} ${formatNumber(document.chunk_count)} chunks`;

                  return (
                    <li key={document.id} className="database-document-list__item">
                      <div className="database-document-card">
                        <div className="database-document-card__row">
                          <div className="database-document-card__title-wrap">
                            <DocumentTextIcon className="database-document-card__icon" />
                            {isEditing ? (
                              <input
                                autoFocus
                                className="database-document-card__input"
                                onChange={(event) => {
                                  setRenameDraft(event.target.value);
                                }}
                                onKeyDown={(event) => {
                                  onDocumentEditorKeyDown(document, event);
                                }}
                                type="text"
                                value={renameDraft}
                              />
                            ) : (
                              <strong className="database-document-card__title" title={document.source_name}>
                                {document.source_name}
                              </strong>
                            )}
                          </div>

                          <div className="database-document-card__actions">
                            {isEditing ? (
                              <>
                                <button
                                  aria-label="Save document name"
                                  className="database-document-card__action-button"
                                  disabled={busy}
                                  onClick={() => {
                                    submitEditingDocument(document);
                                  }}
                                  type="button"
                                >
                                  <CheckIcon />
                                </button>
                                <button
                                  aria-label="Cancel document rename"
                                  className="database-document-card__action-button"
                                  disabled={busy}
                                  onClick={() => {
                                    cancelEditingDocument();
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
                                    label: "Rename source",
                                    icon: PencilSquareIcon,
                                    onSelect: () => {
                                      setEditingDocumentId(document.id);
                                      setRenameDraft(document.source_name);
                                    },
                                  },
                                  {
                                    key: "delete",
                                    label: "Remove source",
                                    icon: TrashIcon,
                                    danger: true,
                                    onSelect: () => {
                                      onDeleteDocument(document);
                                    },
                                  },
                                ]}
                                panelClassName="database-document-menu"
                                triggerClassName="database-document-card__action-button database-document-card__menu-trigger"
                                triggerLabel={`Actions for ${document.source_name}`}
                              />
                            )}
                          </div>
                        </div>
                        <p className="database-document-card__meta" title={metaLabel}>
                          {metaLabel}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState
                compact
                title="No Docs"
              />
            )}
          </section>
        </>
      )}
    </SectionCard>
  );
}
