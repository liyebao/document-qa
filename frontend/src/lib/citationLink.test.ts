import { describe, expect, it } from "vitest";
import type { Citation } from "../api/types";
import { citationFileUrl, citationPage } from "./citationLink";

function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    id: "c1",
    chunk_id: "k1",
    document_id: "doc-1",
    marker_index: 1,
    document_name: "报告.pdf",
    source_location: "第 3 页",
    quote_snapshot: "片段",
    ...overrides,
  };
}

describe("citation links", () => {
  it("extracts the first page from a page range", () => {
    expect(citationPage("第 76–78 页")).toBe(76);
    expect(citationPage("第 12 页")).toBe(12);
  });

  it("returns null for locations without a page number", () => {
    expect(citationPage("第一章 > 1.1 连接查询")).toBeNull();
    expect(citationPage("正文")).toBeNull();
  });

  it("appends the page anchor so PDF viewers jump directly", () => {
    expect(citationFileUrl(makeCitation())).toBe("/api/documents/doc-1/file#page=3");
  });

  it("omits the anchor when the document has no page", () => {
    const url = citationFileUrl(makeCitation({ source_location: "正文" }));

    expect(url).toBe("/api/documents/doc-1/file");
  });

  it("returns null when the source document is gone", () => {
    expect(citationFileUrl(makeCitation({ document_id: null }))).toBeNull();
  });
});
