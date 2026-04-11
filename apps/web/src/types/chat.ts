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

export type MessageRole = "system" | "user" | "assistant" | "tool";

export interface MessageRecord {
  id: string;
  role: MessageRole;
  content: string;
  message_type?: string | null;
  workflow_turn_id?: string | null;
  tool_name?: string | null;
  token_usage?: TokenUsage | null;
  pending?: boolean;
  workflow?: WorkflowSnapshot | null;
}

export interface SessionState {
  session: SessionSummary;
  messages: MessageRecord[];
}

export interface DatabaseRecord {
  id: string;
  name: string;
  collection_name: string;
  embedding_model_name: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface DatabaseState {
  active_database_id: string | null;
  databases: DatabaseRecord[];
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

export interface WorkflowSnapshot {
  workflow_turn_id?: string | null;
  query: string;
  answer: string;
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
