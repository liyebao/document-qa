export interface ProviderInfo {
  key: string;
  label: string;
  embedding_models: string[];
  chat_models: string[];
  rerank_models: string[];
  requires_api_key: boolean;
}

export interface ModelProviderConfig {
  id: string;
  provider_key: string;
  embedding_model: string;
  chat_model: string;
  rerank_model: string;
  status: string;
  key_masked: string;
  last_tested_at: string | null;
  updated_at: string;
  is_embedding_default: boolean;
  is_chat_default: boolean;
}

export interface EffectiveModel {
  config_id: string;
  provider_key: string;
  provider_label: string;
  model: string;
}

export interface ModelProviderSettings {
  providers: ProviderInfo[];
  configs: ModelProviderConfig[];
  preferred_embedding_provider: string | null;
  preferred_chat_provider: string | null;
  effective_embedding: EffectiveModel | null;
  effective_chat: EffectiveModel | null;
  effective_rerank: EffectiveModel | null;
}

export interface ConnectionTestResult {
  ok: boolean;
  embedding_ok: boolean;
  chat_ok: boolean;
  message: string;
}

export interface CollectionOut {
  id: string;
  name: string;
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_dimension: number | null;
  index_version: number;
  created_at: string;
}

export interface CollectionSummary extends CollectionOut {
  document_count: number;
}

export interface DocumentItem {
  id: string;
  collection_id: string;
  filename: string;
  format: string;
  checksum: string;
  version: number;
  status: string;
  failure_reason: string | null;
  source_type: string;
  source_url: string | null;
  fetched_at: string | null;
  is_enabled: boolean;
  is_current: boolean;
  created_at: string;
}

export interface ChunkSnippet {
  chunk_id: string;
  ordinal: number;
  source_location: string;
  text: string;
}

export interface ChunkContext {
  document_id: string;
  document_name: string;
  format: string;
  chunk: ChunkSnippet;
  previous: ChunkSnippet | null;
  next: ChunkSnippet | null;
}

export interface Citation {
  id: string;
  chunk_id: string | null;
  document_id: string | null;
  marker_index: number;
  document_name: string;
  source_location: string;
  quote_snapshot: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  created_at: string;
  citations: Citation[];
}

export interface CollectionReindexResult extends CollectionOut {
  chunk_count: number;
}

export interface ConversationSummary {
  id: string;
  collection_id: string;
  title: string;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
}
