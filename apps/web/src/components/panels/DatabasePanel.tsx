import { ArrowUpTrayIcon, Cog6ToothIcon, CpuChipIcon, DocumentTextIcon } from "@heroicons/react/24/outline";
import { useRef } from "react";

import { Button } from "@/components/common";
import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import { formatNumber } from "@/lib/format";
import type { DatabaseDocumentRecord, DatabaseRecord } from "@/types/chat";

interface DatabasePanelProps {
  activeDatabaseId: string | null;
  busy: boolean;
  databases: DatabaseRecord[];
  documents: DatabaseDocumentRecord[];
  onOpenEmbeddingSettings: () => void;
  onOpenSettings: () => void;
  onUploadFiles: (files: File[]) => void;
  onSelect: (databaseId: string) => void;
}

export function DatabasePanel({
  activeDatabaseId,
  busy,
  databases,
  documents,
  onOpenEmbeddingSettings,
  onOpenSettings,
  onUploadFiles,
  onSelect,
}: DatabasePanelProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const activeDatabase = databases.find((database) => database.id === activeDatabaseId) ?? null;

  return (
    <SectionCard
      eyebrow="Knowledge"
      title="Databases"
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
        <EmptyState compact title="No Databases" description="Create a database in settings to enable local retrieval." />
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
                      <strong className="database-card__title">{database.name}</strong>
                      <span className="database-card__count">{formatNumber(database.document_count)} docs</span>
                    </div>
                    <p className="database-card__meta">{database.embedding_model_name}</p>
                  </button>
                </li>
              );
            })}
          </ul>

          <section className="database-documents" aria-label="Database documents">
            <div className="database-documents__header">
              <div className="database-documents__copy">
                <strong className="database-documents__title">Documents</strong>
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

            {documents.length > 0 ? (
              <ul className="database-document-list">
                {documents.map((document) => (
                  <li key={document.id} className="database-document-list__item">
                    <div className="database-document-card">
                      <div className="database-document-card__row">
                        <div className="database-document-card__title-wrap">
                          <DocumentTextIcon className="database-document-card__icon" />
                          <strong className="database-document-card__title">{document.source_name}</strong>
                        </div>
                        <span className="database-document-card__count">{formatNumber(document.chunk_count)} chunks</span>
                      </div>
                      <p className="database-document-card__meta">
                        {(document.source_type || "unknown").toUpperCase()}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                compact
                title="No Documents"
                description={activeDatabase ? "Upload files here to populate the active database." : "Select a database first."}
              />
            )}
          </section>
        </>
      )}
    </SectionCard>
  );
}
