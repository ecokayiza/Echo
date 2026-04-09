import type { TokenUsage } from "@/types/chat";

const numberFormatter = new Intl.NumberFormat();
const timestampFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatNumber(value: number | null | undefined) {
  return numberFormatter.format(value ?? 0);
}

export function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return timestampFormatter.format(date);
}

export function formatTokenUsage(tokenUsage: TokenUsage | null | undefined) {
  if (!tokenUsage) {
    return "";
  }

  const parts: string[] = [];

  if (typeof tokenUsage.prompt_tokens === "number") {
    parts.push(`Prompt ${formatNumber(tokenUsage.prompt_tokens)}`);
  }
  if (typeof tokenUsage.completion_tokens === "number") {
    parts.push(`Completion ${formatNumber(tokenUsage.completion_tokens)}`);
  }
  if (typeof tokenUsage.prompt_cache_hit_tokens === "number") {
    parts.push(`Cache ${formatNumber(tokenUsage.prompt_cache_hit_tokens)}`);
  }
  if (typeof tokenUsage.total_tokens === "number") {
    parts.push(`Total ${formatNumber(tokenUsage.total_tokens)}`);
  }

  if (parts.length > 0) {
    return parts.join("  |  ");
  }

  return Object.entries(tokenUsage)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .map(([key, value]) => `${key} ${formatNumber(value)}`)
    .join("  |  ");
}

export function formatTokenTotal(tokenUsage: TokenUsage | null | undefined) {
  if (typeof tokenUsage?.total_tokens === "number") {
    return `Token ${formatNumber(tokenUsage.total_tokens)}`;
  }

  const numericEntry = Object.values(tokenUsage ?? {}).find((value): value is number => typeof value === "number");
  return typeof numericEntry === "number" ? `Token ${formatNumber(numericEntry)}` : "";
}

export function trimOrNull(value: string | null | undefined) {
  const trimmed = value?.trim() ?? "";
  return trimmed.length > 0 ? trimmed : null;
}
