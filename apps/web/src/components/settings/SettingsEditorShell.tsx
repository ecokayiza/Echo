import { PlusIcon } from "@heroicons/react/24/outline";
import type { ReactNode } from "react";

import { Button } from "@/components/common";

interface SettingsEditorShellProps {
  actionLabel: string;
  children: ReactNode;
  emptyTitle: string;
  eyebrow: string;
  onAdd: () => void;
  title: string;
}

export function SettingsEditorShell({
  actionLabel,
  children,
  emptyTitle,
  eyebrow,
  onAdd,
  title,
}: SettingsEditorShellProps) {
  return (
    <div className="settings-editor">
      <header className="settings-editor__header">
        <div>
          <p className="settings-page__eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
        <Button onClick={onAdd} variant="primary">
          <PlusIcon />
          {actionLabel}
        </Button>
      </header>
      <div className="settings-editor__grid" aria-label={emptyTitle}>
        {children}
      </div>
    </div>
  );
}

export function EmptySettingsDetail({ title }: { title: string }) {
  return (
    <div className="settings-detail settings-detail--empty">
      <h3>{title}</h3>
    </div>
  );
}
