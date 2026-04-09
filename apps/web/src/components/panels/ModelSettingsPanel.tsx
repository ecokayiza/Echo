import { Button } from "@/components/common/Button";
import { Field } from "@/components/common/Field";
import { SectionCard } from "@/components/common/SectionCard";
import type { ChatSettings } from "@/types/chat";

interface ModelSettingsPanelProps {
  activeModelName: string;
  busy: boolean;
  settings: ChatSettings;
  onChange: <Key extends keyof ChatSettings>(key: Key, value: ChatSettings[Key]) => void;
  onSave: () => void;
}

export function ModelSettingsPanel({
  activeModelName,
  busy,
  onChange,
  onSave,
  settings,
}: ModelSettingsPanelProps) {
  return (
    <SectionCard
      eyebrow="Model"
      title="Generation"
      description="Model Configuration"
      actions={
        <Button disabled={busy} onClick={onSave} size="sm" variant="primary">
          Save
        </Button>
      }
    >
      <div className="model-overview">
        <span className="model-overview__label">Active Model</span>
        <strong className="model-overview__value">{activeModelName}</strong>
      </div>

      <div className="form-grid">
        <Field htmlFor="temperature" label="Temperature">
          <div className="temperature-control">
            <input
              disabled={busy}
              id="temperature"
              max="2"
              min="0"
              name="temperature"
              onChange={(event) => {
                onChange("temperature", Number.parseFloat(event.target.value || "1"));
              }}
              step="0.1"
              type="range"
              value={String(settings.temperature)}
            />
            <input
              disabled={busy}
              inputMode="decimal"
              max="2"
              min="0"
              onChange={(event) => {
                onChange("temperature", Number.parseFloat(event.target.value || "1"));
              }}
              step="0.1"
              type="number"
              value={String(settings.temperature)}
            />
          </div>
        </Field>
      </div>
    </SectionCard>
  );
}
