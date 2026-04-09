interface EmptyStateProps {
  title: string;
  description: string;
  compact?: boolean;
}

export function EmptyState({ compact = false, description, title }: EmptyStateProps) {
  return (
    <div className={`empty-state${compact ? " empty-state--compact" : ""}`}>
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__description">{description}</p>
    </div>
  );
}
