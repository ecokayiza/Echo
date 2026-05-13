import { BeakerIcon, TrashIcon } from "@heroicons/react/24/outline";

import { Button } from "@/components/common";

import { StatusPills } from "./StatusPills";

interface SettingsDetailHeaderProps {
  active: boolean;
  activeLabel?: string;
  canRemove: boolean;
  duplicate?: boolean;
  inactiveActionLabel?: string;
  onMakeActive: () => void;
  onRemove: () => void;
  onTestApi?: () => void;
  protectedLabel?: string | null;
  statusFlags?: Array<string | null | false | undefined>;
  testApiDisabled?: boolean;
  title: string;
}

export function SettingsDetailHeader({
  active,
  activeLabel = "Active",
  canRemove,
  duplicate = false,
  inactiveActionLabel = "Make Active",
  onMakeActive,
  onRemove,
  onTestApi,
  protectedLabel = null,
  statusFlags = [],
  testApiDisabled = false,
  title,
}: SettingsDetailHeaderProps) {
  return (
    <header className="settings-detail__header">
      <div className="settings-detail__title-block">
        <h3>{title}</h3>
        <StatusPills
          flags={[active ? activeLabel : null, protectedLabel, duplicate ? "Duplicate name" : null, ...statusFlags]}
        />
      </div>
      <div className="settings-detail__actions">
        {onTestApi ? (
          <Button disabled={testApiDisabled} onClick={onTestApi} size="sm" variant="secondary">
            <BeakerIcon />
            Test API
          </Button>
        ) : null}
        <Button disabled={active} onClick={onMakeActive} size="sm" variant="secondary">
          {active ? activeLabel : inactiveActionLabel}
        </Button>
        <Button disabled={!canRemove} onClick={onRemove} size="sm" variant="danger">
          <TrashIcon />
          Delete
        </Button>
      </div>
    </header>
  );
}
