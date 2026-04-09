import type { ChatSettings, HealthResponse, MetaResponse } from "@/types/chat";

import { trimOrNull } from "./format";

export function sanitizeSettings(
  settings: ChatSettings,
  meta: MetaResponse | null,
  health: HealthResponse | null
): ChatSettings {
  const defaults = meta?.default_chat_settings;
  const temperature = Number.isFinite(settings.temperature)
    ? settings.temperature
    : (defaults?.temperature ?? 1);

  return {
    provider: trimOrNull(settings.provider) ?? defaults?.provider ?? "openai_compatible",
    model: trimOrNull(settings.model) ?? defaults?.model ?? health?.model ?? null,
    api_key: trimOrNull(settings.api_key),
    base_url: trimOrNull(settings.base_url) ?? defaults?.base_url ?? null,
    temperature,
  };
}
