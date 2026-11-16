import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Message } from "../api/types";
import { toCitationLinks } from "../lib/citationMarkdown";
import { ChatMessage } from "./ChatMessage";

const ASSISTANT_MESSAGE: Message = {
  id: "message-1",
  role: "assistant",
  content: "项目存在进度风险[1]。",
  status: "completed",
  created_at: "2026-11-12T10:00:00Z",
  citations: [
    {
      id: "citation-1",
      chunk_id: "chunk-1",
      document_id: "document-1",
      marker_index: 1,
      document_name: "项目风险报告.pdf",
      source_location: "第 3 页",
      quote_snapshot: "项目存在进度风险，需要提前准备资源。",
    },
  ],
};

describe("ChatMessage", () => {
  it("renders citation details", () => {
    const html = renderToStaticMarkup(<ChatMessage message={ASSISTANT_MESSAGE} />);

    expect(html).toContain("项目存在进度风险");
    expect(html).toContain("项目风险报告.pdf");
    expect(html).toContain("第 3 页");
    expect(html).toContain("打开原文");
    expect(html).toContain("/api/documents/document-1/file#page=3");
    expect(html).toContain("项目存在进度风险，需要提前准备资源。");
  });

  it("shows an evidence warning for insufficient answers", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...ASSISTANT_MESSAGE,
          content: "当前资料无法确认。",
          status: "insufficient",
          citations: [],
        }}
      />,
    );

    expect(html).toContain("本次回答未找到足够的资料依据");
  });

  it("shows a retry hint for failed answers", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...ASSISTANT_MESSAGE,
          content: "回答生成失败，请稍后重试。",
          status: "failed",
          citations: [],
        }}
      />,
    );

    expect(html).toContain("本次回答生成失败");
  });

  it("renders user messages without citation blocks", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...ASSISTANT_MESSAGE,
          role: "user",
          content: "项目风险是什么？",
          citations: [],
        }}
      />,
    );

    expect(html).toContain("项目风险是什么？");
    expect(html).not.toContain("引用来源");
  });

  it("renders markdown blocks instead of raw syntax", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...ASSISTANT_MESSAGE,
          content: "## 结论\n\n- **进度风险**：需要提前准备资源[1]\n- 资料完整",
        }}
      />,
    );

    expect(html).toContain("<h2");
    expect(html).toContain("<li");
    expect(html).toContain("<strong");
    expect(html).not.toContain("**进度风险**");
    expect(html).not.toContain("## 结论");
  });

  it("turns citation markers into source badges", () => {
    const html = renderToStaticMarkup(<ChatMessage message={ASSISTANT_MESSAGE} />);

    expect(html).toContain("/api/documents/document-1/file#page=3");
    expect(html).toContain('aria-label="引用 1：项目风险报告.pdf 第 3 页"');
    expect(html).toContain(">1</a>");
  });

  it("renders fenced code as a card with language label and copy", () => {
    const html = renderToStaticMarkup(
      <ChatMessage
        message={{
          ...ASSISTANT_MESSAGE,
          content: "```sql\nSELECT * FROM emp;\n```",
          citations: [],
        }}
      />,
    );

    expect(html).toContain(">sql<");
    expect(html).toContain("复制");
    expect(html).toContain("hljs-keyword");
    expect(html).toContain("SELECT");
  });

  it("does not rewrite a citation marker that is already a link", () => {
    expect(toCitationLinks("见[1]")).toBe("见[1](cite:1)");
    expect(toCitationLinks("见[1](cite:1)")).toBe("见[1](cite:1)");
  });
});
