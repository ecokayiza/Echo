import { CheckCircleIcon } from "@heroicons/react/24/outline";
import type { ReactNode } from "react";

import { Field } from "@/components/common";

import { SettingsDetailHeader } from "./SettingsDetailHeader";
import { EmptySettingsDetail, SettingsEditorShell } from "./SettingsEditorShell";
import { SettingsItemList } from "./SettingsItemList";
import { hasDuplicateName } from "./settings-utils";

interface ModelBase {
  api_key: string | null;
  base_url: string | null;
  model: string | null;
  name: string;
}

export interface ModelFieldContext<T extends ModelBase> {
  busy: boolean;
  index: number;
  model: T;
  onUpdate: <Key extends keyof T>(index: number, key: Key, value: T[Key]) => void;
}

interface ModelSettingsSectionProps<T extends ModelBase> {
  actionLabel: string;
  activeName: string | null;
  busy: boolean;
  emptyDetailTitle: string;
  emptyListLabel: string;
  eyebrow?: string;
  idPrefix: string;
  models: T[];
  onAdd: () => void;
  onChangeActive: (name: string) => void;
  onRemove: (index: number) => void;
  onSelect: (index: number) => void;
  onTestApi?: (model: T, index: number) => void;
  onUpdate: <Key extends keyof T>(index: number, key: Key, value: T[Key]) => void;
  renderSpecificFields?: (context: ModelFieldContext<T>) => ReactNode;
  selectedIndex: number;
  title: string;
}

export function ModelSettingsSection<T extends ModelBase>({
  actionLabel,
  activeName,
  busy,
  emptyDetailTitle,
  emptyListLabel,
  eyebrow = "Models",
  idPrefix,
  models,
  onAdd,
  onChangeActive,
  onRemove,
  onSelect,
  onTestApi,
  onUpdate,
  renderSpecificFields,
  selectedIndex,
  title,
}: ModelSettingsSectionProps<T>) {
  const model = models[selectedIndex] ?? null;
  const duplicateName = hasDuplicateName(models, selectedIndex);

  return (
    <SettingsEditorShell actionLabel={actionLabel} emptyTitle={emptyDetailTitle} eyebrow={eyebrow} onAdd={onAdd} title={title}>
      <SettingsItemList
        emptyLabel={emptyListLabel}
        getKey={(item, index) => `${item.name}-${index}`}
        items={models}
        onSelect={onSelect}
        renderDescription={(item) => (item.name === activeName ? "Active model" : "Configured")}
        renderTitle={(item) => item.name || "Unnamed Model"}
        renderTrailing={(item) => (item.name === activeName ? <CheckCircleIcon /> : null)}
        selectedIndex={selectedIndex}
      />

      {model ? (
        <div className="settings-detail">
          <SettingsDetailHeader
            active={model.name === activeName}
            canRemove={models.length > 1}
            duplicate={duplicateName}
            onMakeActive={() => {
              onChangeActive(model.name);
            }}
            onRemove={() => {
              onRemove(selectedIndex);
            }}
            onTestApi={
              onTestApi
                ? () => {
                    onTestApi(model, selectedIndex);
                  }
                : undefined
            }
            testApiDisabled={busy || !model.api_key || !model.model}
            title={model.name || "Unnamed Model"}
          />

          <div className="form-grid form-grid--two">
            <Field htmlFor={`${idPrefix}-name`} label="Display Name">
              <input
                disabled={busy}
                id={`${idPrefix}-name`}
                onChange={(event) => {
                  onUpdate(selectedIndex, "name", event.target.value);
                }}
                value={model.name}
              />
            </Field>
            <Field htmlFor={`${idPrefix}-request`} label="Request Model">
              <input
                disabled={busy}
                id={`${idPrefix}-request`}
                onChange={(event) => {
                  onUpdate(selectedIndex, "model", event.target.value || null);
                }}
                value={model.model ?? ""}
              />
            </Field>
            <Field htmlFor={`${idPrefix}-url`} label="Base URL">
              <input
                disabled={busy}
                id={`${idPrefix}-url`}
                onChange={(event) => {
                  onUpdate(selectedIndex, "base_url", event.target.value || null);
                }}
                value={model.base_url ?? ""}
              />
            </Field>
            <Field htmlFor={`${idPrefix}-key`} label="API Key">
              <input
                disabled={busy}
                id={`${idPrefix}-key`}
                onChange={(event) => {
                  onUpdate(selectedIndex, "api_key", event.target.value || null);
                }}
                type="password"
                value={model.api_key ?? ""}
              />
            </Field>
            {renderSpecificFields?.({ busy, index: selectedIndex, model, onUpdate })}
          </div>
        </div>
      ) : (
        <EmptySettingsDetail title={emptyDetailTitle} />
      )}
    </SettingsEditorShell>
  );
}
