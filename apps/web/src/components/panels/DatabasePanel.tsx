import { Cog6ToothIcon } from "@heroicons/react/24/outline";

import { EmptyState } from "@/components/common/EmptyState";
import { SectionCard } from "@/components/common/SectionCard";
import { formatNumber } from "@/lib/format";
import type { DatabaseRecord } from "@/types/chat";

interface DatabasePanelProps {
  activeDatabaseId: string | null;
  busy: boolean;
  databases: DatabaseRecord[];
  onOpenSettings: () => void;
  onSelect: (databaseId: string) => void;
}

export function DatabasePanel({
  activeDatabaseId,
  busy,
  databases,
  onOpenSettings,
  onSelect,
}: DatabasePanelProps) {
  return (
    <SectionCard
      eyebrow="Knowledge"
      title="Databases"
      actions={
        <button
          aria-label="Open database settings"
          className="model-settings-button"
          disabled={busy}
          onClick={onOpenSettings}
          type="button"
        >
          <Cog6ToothIcon />
        </button>
      }
    >
      {databases.length === 0 ? (
        <EmptyState compact title="No Databases" description="Create a database in settings to enable local retrieval." />
      ) : (
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
      )}
    </SectionCard>
  );
}
