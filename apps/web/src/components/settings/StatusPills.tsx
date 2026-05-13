interface StatusPillsProps {
  flags: Array<string | null | false | undefined>;
}

export function StatusPills({ flags }: StatusPillsProps) {
  const visible = flags.filter(Boolean) as string[];
  if (visible.length === 0) {
    return null;
  }

  return (
    <span className="settings-pills">
      {visible.map((flag) => (
        <em key={flag}>{flag}</em>
      ))}
    </span>
  );
}
