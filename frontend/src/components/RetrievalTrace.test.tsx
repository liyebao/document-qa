import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { RetrievalTraceData } from "../api/types";
import { RetrievalTrace } from "./RetrievalTrace";

const TRACE: RetrievalTraceData = {
  queries: ["七步全景", "检索策略"],
  documents: [{ name: "资料A.pdf", location: "第 1–2 页", marker: 1 }],
  searches: 2,
  expanded: 0,
  full_scan_chunks: 12,
  reference_chunks: 2,
};

describe("RetrievalTrace", () => {
  it("renders a collapsed trace with queries and browsed documents", () => {
    const html = renderToStaticMarkup(<RetrievalTrace trace={TRACE} />);

    expect(html).toContain("检索过程");
    expect(html).toContain("已通读 12 处原文");
    expect(html).toContain("按编号补证 2 处");
    expect(html).toContain("七步全景");
    expect(html).toContain("资料A.pdf");
    expect(html).toContain("第 1–2 页");
    expect(html).toContain("<details");
    expect(html).not.toContain("<details open");
  });

  it("reads the legacy cross_doc_chunks field for old messages", () => {
    const html = renderToStaticMarkup(
      <RetrievalTrace trace={{ ...TRACE, reference_chunks: undefined, cross_doc_chunks: 1 }} />,
    );

    expect(html).toContain("按编号补证 1 处");
  });

  it("renders nothing for legacy messages with an empty trace object", () => {
    const html = renderToStaticMarkup(
      <RetrievalTrace trace={{} as RetrievalTraceData} />,
    );

    expect(html).toBe("");
  });
});
