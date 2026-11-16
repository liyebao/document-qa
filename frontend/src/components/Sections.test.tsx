import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type {
  CollectionSummary,
  DocumentItem,
  ModelProviderSettings,
} from "../api/types";
import { CollectionHeader } from "./CollectionHeader";
import { DocumentSection } from "./DocumentSection";
import { ModelRoles } from "./ModelRoles";
import { ProviderEditor } from "./ProviderEditor";
import { SavedConfigList } from "./SavedConfigList";

const COLLECTION: CollectionSummary = {
  id: "collection-1",
  name: "毕业设计调研",
  embedding_provider: "openai",
  embedding_model: "text-embedding-3-small",
  embedding_dimension: 1536,
  index_version: 2,
  created_at: "2026-11-12T10:00:00Z",
  document_count: 2,
};

const DOCUMENT: DocumentItem = {
  id: "document-1",
  collection_id: "collection-1",
  filename: "项目风险报告.pdf",
  format: "pdf",
  checksum: "abc",
  version: 1,
  status: "ready",
  failure_reason: null,
  source_type: "upload",
  source_url: null,
  fetched_at: null,
  is_enabled: true,
  is_current: true,
  created_at: "2026-11-12T10:00:00Z",
};

const SETTINGS: ModelProviderSettings = {
  providers: [
    {
      key: "openai",
      label: "OpenAI",
      embedding_models: ["text-embedding-3-small"],
      chat_models: ["gpt-4o-mini"],
      rerank_models: ["BAAI/bge-reranker-v2-m3"],
      requires_api_key: true,
    },
  ],
  configs: [
    {
      id: "config-1",
      provider_key: "openai",
      embedding_model: "text-embedding-3-small",
      chat_model: "gpt-4o-mini",
      rerank_model: "",
      status: "ok",
      key_masked: "sk-****abcd",
      last_tested_at: "2026-11-12T10:00:00Z",
      updated_at: "2026-11-12T10:00:00Z",
      is_embedding_default: true,
      is_chat_default: true,
    },
  ],
  preferred_embedding_provider: "openai",
  preferred_chat_provider: "openai",
  effective_embedding: {
    config_id: "config-1",
    provider_key: "openai",
    provider_label: "OpenAI",
    model: "text-embedding-3-small",
  },
  effective_chat: {
    config_id: "config-1",
    provider_key: "openai",
    provider_label: "OpenAI",
    model: "gpt-4o-mini",
  },
  effective_rerank: null,
};

const noop = () => undefined;
const noopAsync = async () => undefined;

describe("page sections", () => {
  it("renders collection header with index version", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <CollectionHeader
          collection={COLLECTION}
          documentCount={2}
          reindexing={false}
          onReindex={noop}
          onRename={noop}
        />
      </MemoryRouter>,
    );

    expect(html).toContain("毕业设计调研");
    expect(html).toContain("索引 v2");
    expect(html).toContain("重建索引");
  });

  it("renders file list and upload control", () => {
    const html = renderToStaticMarkup(
      <DocumentSection
        documents={[DOCUMENT]}
        uploading={false}
        importing={false}
        onUpload={noop}
        onCreateText={noopAsync}
        onImportUrl={noopAsync}
        onReplace={noop}
        onToggle={noop}
        onRetry={noop}
        onDelete={noop}
      />,
    );

    expect(html).toContain("项目风险报告.pdf");
    expect(html).toContain("添加文件");
    expect(html).toContain("粘贴文本");
    expect(html).toContain("导入链接");
  });

  it("renders provider editor and saved configuration", () => {
    const editor = renderToStaticMarkup(
      <ProviderEditor settings={SETTINGS} onChanged={noop} />,
    );
    const saved = renderToStaticMarkup(
      <SavedConfigList
        settings={SETTINGS}
        testingId={null}
        onTest={noop}
        onDelete={noop}
      />,
    );

    expect(editor).toContain("保存修改");
    expect(editor).toContain("更改模型");
    expect(editor).toContain("OpenAI");
    expect(saved).toContain("sk-****abcd");
    expect(saved).toContain("连接正常");
  });

  it("renders effective retrieval and chat models", () => {
    const html = renderToStaticMarkup(
      <ModelRoles settings={SETTINGS} busy={false} onRoleChange={noop} />,
    );

    expect(html).toContain("检索");
    expect(html).toContain("回答");
    expect(html).toContain("text-embedding-3-small");
    expect(html).toContain("gpt-4o-mini");
    expect(html).toContain("重排未启用");
  });
});
