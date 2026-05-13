import { Field } from "@/components/common";
import { normalizeSkillName } from "@/lib/skill-settings";
import type { SkillRecord } from "@/types/chat";

import { SettingsDetailHeader } from "./SettingsDetailHeader";
import { EmptySettingsDetail, SettingsEditorShell } from "./SettingsEditorShell";
import { SettingsItemList } from "./SettingsItemList";
import { StatusPills } from "./StatusPills";
import { hasDuplicateName } from "./settings-utils";

interface SkillSettingsSectionProps {
  busy: boolean;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onSelect: (index: number) => void;
  onUpdate: <Key extends keyof SkillRecord>(index: number, key: Key, value: SkillRecord[Key]) => void;
  selectedIndex: number;
  skills: SkillRecord[];
}

export function SkillSettingsSection({
  busy,
  onAdd,
  onRemove,
  onSelect,
  onUpdate,
  selectedIndex,
  skills,
}: SkillSettingsSectionProps) {
  const skill = skills[selectedIndex] ?? null;
  const duplicateName = hasDuplicateName(skills, selectedIndex);

  return (
    <SettingsEditorShell actionLabel="Add Skill" emptyTitle="No skill selected" eyebrow="Skills" onAdd={onAdd} title="Skills">
      <SettingsItemList
        emptyLabel="No skills configured"
        getKey={(item, index) => `${item.name}-${index}`}
        items={skills}
        onSelect={onSelect}
        renderDescription={(item) => item.description}
        renderTitle={(item) => item.name || "unnamed-skill"}
        renderTrailing={(item) => (
          <StatusPills flags={[item.enabled ? "Enabled" : "Disabled", item.default ? "Default" : null, item.protected ? "Protected" : null]} />
        )}
        selectedIndex={selectedIndex}
      />

      {skill ? (
        <div className="settings-detail settings-detail--skill">
          <SettingsDetailHeader
            active={skill.enabled}
            activeLabel={skill.enabled ? "Enabled" : "Disabled"}
            canRemove={!skill.protected}
            duplicate={duplicateName}
            inactiveActionLabel={skill.enabled ? "Disable" : "Enable"}
            onMakeActive={() => {
              onUpdate(selectedIndex, "enabled", !skill.enabled);
            }}
            onRemove={() => {
              onRemove(selectedIndex);
            }}
            protectedLabel={skill.protected ? "Built-in skill" : null}
            statusFlags={[!skill.enabled ? "Disabled" : null, skill.default ? "Default" : null]}
            title={skill.name || "unnamed-skill"}
          />

          <div className="form-grid">
            <Field htmlFor="skill-name" hint="Use lowercase letters, numbers, dashes, or underscores." label="Name">
              <input
                disabled={busy || skill.protected}
                id="skill-name"
                onChange={(event) => {
                  onUpdate(selectedIndex, "name", normalizeSkillName(event.target.value));
                }}
                value={skill.name}
              />
            </Field>

            <Field htmlFor="skill-description" label="Description">
              <textarea
                className="settings-textarea"
                disabled={busy}
                id="skill-description"
                onChange={(event) => {
                  onUpdate(selectedIndex, "description", event.target.value);
                }}
                rows={2}
                value={skill.description}
              />
            </Field>
          </div>

          <div className="settings-toggle-row">
            <label className="settings-toggle">
              <input
                checked={skill.enabled}
                disabled={busy}
                onChange={(event) => {
                  onUpdate(selectedIndex, "enabled", event.target.checked);
                }}
                type="checkbox"
              />
              <span>Enabled</span>
            </label>
            <label className="settings-toggle">
              <input
                checked={skill.default}
                disabled={busy || !skill.enabled}
                onChange={(event) => {
                  onUpdate(selectedIndex, "default", event.target.checked);
                }}
                type="checkbox"
              />
              <span>Default prompt skill</span>
            </label>
          </div>

          <Field htmlFor="skill-content" label="Markdown Instructions">
            <textarea
              className="settings-skill-editor"
              disabled={busy}
              id="skill-content"
              onChange={(event) => {
                onUpdate(selectedIndex, "content", event.target.value);
              }}
              spellCheck={false}
              value={skill.content}
            />
          </Field>
        </div>
      ) : (
        <EmptySettingsDetail title="No skill selected" />
      )}
    </SettingsEditorShell>
  );
}
