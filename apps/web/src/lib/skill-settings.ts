import type { SkillRecord, SkillSettingsDocument } from "@/types/chat";

import { trimOrNull } from "./format";

export function createEmptySkill(index: number, initial?: Partial<SkillRecord>): SkillRecord {
  return normalizeSkillRecord(
    {
      name: initial?.name ?? `custom-skill-${index}`,
      description: initial?.description ?? "Describe when this skill should be used.",
      content: initial?.content ?? "# Custom Skill\n\nAdd the workflow guidance for this skill.",
      enabled: initial?.enabled ?? true,
      default: initial?.default ?? false,
      protected: initial?.protected ?? false,
    },
    index
  );
}

export function normalizeSkillName(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "");
}

export function normalizeSkillRecord(
  record: Partial<SkillRecord> | SkillRecord | null | undefined,
  index = 1
): SkillRecord {
  const name = normalizeSkillName(record?.name ?? "") || `custom-skill-${index}`;
  const enabled = record?.enabled ?? true;

  return {
    name,
    description: trimOrNull(record?.description) ?? "Describe when this skill should be used.",
    content: trimOrNull(record?.content) ?? "# Custom Skill\n\nAdd the workflow guidance for this skill.",
    enabled,
    default: enabled ? Boolean(record?.default) : false,
    protected: Boolean(record?.protected),
  };
}

export function normalizeSkillSettingsDocument(
  document: Partial<SkillSettingsDocument> | SkillSettingsDocument | null | undefined
): SkillSettingsDocument {
  const skills = Array.isArray(document?.skills)
    ? document.skills.map((skill, index) => normalizeSkillRecord(skill, index + 1))
    : [];

  return { skills };
}
