export interface TokenUsage {
  prompt_tokens?: number;
  prompt_cache_hit_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  [key: string]: number | undefined;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
  token_usage: TokenUsage;
  total_tokens: number;
}

export type MessageRole = "system" | "user" | "assistant";

export interface MessageRecord {
  id: string;
  role: MessageRole;
  content: string;
  token_usage?: TokenUsage | null;
  pending?: boolean;
  workflow?: WorkflowSnapshot | null;
}

export interface SessionState {
  session: SessionSummary;
  messages: MessageRecord[];
}

export interface WorkflowNodeStatus {
  node: string;
  status: string;
  detail?: string | null;
}

export interface WorkflowLog {
  level: string;
  node?: string | null;
  message: string;
}

export interface WorkflowTraceEntry {
  node: string;
  output?: string;
  decision?: Record<string, unknown>;
  tool_result?: Record<string, unknown>;
}

export interface WorkflowSnapshot {
  query: string;
  requested_skill?: string | null;
  loaded_skills?: Array<Record<string, unknown>>;
  context_items: Array<Record<string, unknown>>;
  trace?: WorkflowTraceEntry[];
  answer: string;
  token_usage?: TokenUsage | null;
  status: string;
  node_statuses: WorkflowNodeStatus[];
  active_node: string | null;
  logs: WorkflowLog[];
  errors: string[];
}

export interface ChatResponse extends SessionState {
  reply: string;
  token_usage?: TokenUsage | null;
  workflow?: WorkflowSnapshot | null;
}

export interface HealthResponse {
  status: string;
  model: string | null;
}

export interface ChatModelConfig {
  name: string;
  model: string | null;
  api_key: string | null;
  base_url: string | null;
  temperature: number;
  top_p: number | null;
  enable_thinking: boolean | null;
}

export interface EmbeddingModelConfig {
  name: string;
  model: string | null;
  api_key: string | null;
  base_url: string | null;
}

export interface ModelSettingsDocument {
  active_chat_model: string | null;
  active_embedding_model: string | null;
  chat_models: ChatModelConfig[];
  embedding_models: EmbeddingModelConfig[];
}

export interface MetaResponse {
  workflow_statuses: string[];
  workflow_steps: string[];
  default_system_prompt: string;
}

export interface ConfirmDialogState {
  title: string;
  description: string;
  confirmLabel: string;
  tone?: "danger" | "secondary";
  onConfirm: () => Promise<void>;
}
