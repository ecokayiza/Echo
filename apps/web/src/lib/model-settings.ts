import type { ChatModelConfig, EmbeddingModelConfig, ModelSettingsDocument } from "@/types/chat";

import { trimOrNull } from "./format";

function normalizeNumber(value: number | null | undefined, fallback: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeBoolean(value: boolean | null | undefined) {
  return typeof value === "boolean" ? value : null;
}

export function createEmptyChatModel(index: number): ChatModelConfig {
  return {
    name: `Chat Model ${index}`,
    model: null,
    api_key: null,
    base_url: null,
    temperature: 1,
    top_p: null,
    enable_thinking: false,
  };
}

export function createEmptyEmbeddingModel(index: number): EmbeddingModelConfig {
  return {
    name: `Embedding Model ${index}`,
    model: null,
    api_key: null,
    base_url: null,
  };
}

export function normalizeChatModelConfig(
  config: Partial<ChatModelConfig> | ChatModelConfig | null | undefined,
  index = 1
): ChatModelConfig {
  return {
    name: trimOrNull(config?.name) ?? trimOrNull(config?.model) ?? `Chat Model ${index}`,
    model: trimOrNull(config?.model),
    api_key: trimOrNull(config?.api_key),
    base_url: trimOrNull(config?.base_url),
    temperature: normalizeNumber(config?.temperature, 1) ?? 1,
    top_p: normalizeNumber(config?.top_p, null),
    enable_thinking: normalizeBoolean(config?.enable_thinking),
  };
}

export function normalizeEmbeddingModelConfig(
  config: Partial<EmbeddingModelConfig> | EmbeddingModelConfig | null | undefined,
  index = 1
): EmbeddingModelConfig {
  return {
    name: trimOrNull(config?.name) ?? trimOrNull(config?.model) ?? `Embedding Model ${index}`,
    model: trimOrNull(config?.model),
    api_key: trimOrNull(config?.api_key),
    base_url: trimOrNull(config?.base_url),
  };
}

export function normalizeModelSettingsDocument(
  config: Partial<ModelSettingsDocument> | ModelSettingsDocument | null | undefined
): ModelSettingsDocument {
  const chatModels = Array.isArray(config?.chat_models)
    ? config.chat_models.map((item, index) => normalizeChatModelConfig(item, index + 1))
    : [];
  const embeddingModels = Array.isArray(config?.embedding_models)
    ? config.embedding_models.map((item, index) => normalizeEmbeddingModelConfig(item, index + 1))
    : [];

  const activeChatModel = trimOrNull(config?.active_chat_model);
  const activeEmbeddingModel = trimOrNull(config?.active_embedding_model);

  return {
    active_chat_model:
      chatModels.length === 0
        ? null
        : chatModels.some((item) => item.name === activeChatModel)
          ? activeChatModel
          : chatModels[0].name,
    active_embedding_model:
      embeddingModels.length === 0
        ? null
        : embeddingModels.some((item) => item.name === activeEmbeddingModel)
          ? activeEmbeddingModel
          : embeddingModels[0].name,
    chat_models: chatModels,
    embedding_models: embeddingModels,
  };
}

export function getActiveChatModel(config: ModelSettingsDocument): ChatModelConfig | null {
  return config.chat_models.find((item) => item.name === config.active_chat_model) ?? config.chat_models[0] ?? null;
}

export function getActiveEmbeddingModel(config: ModelSettingsDocument): EmbeddingModelConfig | null {
  return (
    config.embedding_models.find((item) => item.name === config.active_embedding_model) ??
    config.embedding_models[0] ??
    null
  );
}
