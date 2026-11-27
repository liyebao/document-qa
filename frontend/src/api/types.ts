export interface ProviderInfo {
  key: string;
  label: string;
  embedding_models: string[];
  chat_models: string[];
  rerank_models: string[];
  requires_api_key: boolean;
}

/** 本地服务商（Ollama）实际已下载的模型；reachable=false 表示连不上本地服务。 */
export interface ProviderModels {
  provider_key: string;
  reachable: boolean;
  installed: string[];
  message: string;
}

/** 预览用的单个片段：chunk_id 用于把引用精确定位到某一块。 */
export interface DocumentPreviewBlock {
  chunk_id: string;
  ordinal: number;
  source_location: string;
  text: string;
}

export interface DocumentPreview {
  document_id: string;
  document_name: string;
  format: string;
  truncated: boolean;
  blocks: DocumentPreviewBlock[];
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

export interface Citation {
  id: string;
  chunk_id: string | null;
  document_id: string | null;
  marker_index: number;
  document_name: string;
  source_location: string;
  quote_snapshot: string;
}

export interface RetrievalTraceDocument {
  name: string;
  location: string;
  marker: number;
}

export interface RetrievalTraceData {
  queries: string[];
  documents: RetrievalTraceDocument[];
  searches: number;
  expanded: number;
  full_scan_chunks?: number;
  /** 按编号补全的原文条数（问题点名条/章/节时补进来的部分）。 */
  reference_chunks?: number;
  /** @deprecated 旧消息只有这个字段；新消息写 reference_chunks。 */
  cross_doc_chunks?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  created_at: string;
  citations: Citation[];
  retrieval_trace?: RetrievalTraceData;
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

export interface ConversationListItem extends ConversationSummary {
  /** 所属资料集名称，侧边栏「最近」用来标明上下文。 */
  collection_name: string;
  /** 最近活动时间（最后一条消息时间，没有消息时等于 created_at）。 */
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Message[];
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
}
