import { Cog6ToothIcon } from "@heroicons/react/24/outline";

import { Field } from "@/components/common/Field";
import { SectionCard } from "@/components/common/SectionCard";

interface ModelSettingsPanelProps {
  activeModelName: string;
  busy: boolean;
  modelNames: string[];
  onOpenSettings: () => void;
  onSelectActiveModel: (name: string) => void | Promise<void>;
}

export function ModelSettingsPanel({
  activeModelName,
  busy,
  modelNames,
  onOpenSettings,
  onSelectActiveModel,
}: ModelSettingsPanelProps) {
  const hasModels = modelNames.length > 0;

  return (
    <SectionCard
      eyebrow="Model"
      actions={
        <button
          aria-label="Open model settings"
          className="model-settings-button"
          disabled={busy}
          onClick={onOpenSettings}
          type="button"
        >
          <Cog6ToothIcon />
        </button>
      }
    >
      <Field htmlFor="active-model-select" label="Active Model">
        <select
          disabled={busy || !hasModels}
          id="active-model-select"
          onChange={(event) => {
            void onSelectActiveModel(event.target.value);
          }}
          value={hasModels ? activeModelName : ""}
        >
          {hasModels ? (
            modelNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))
          ) : (
            <option value="">No models configured</option>
          )}
        </select>
      </Field>
    </SectionCard>
  );
}
