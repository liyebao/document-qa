import { useMemo } from "react";
import type { Element, ElementContent } from "hast";
import ReactMarkdown, { type Components, defaultUrlTransform } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import type { Citation } from "../api/types";
import { citationPage } from "../lib/citationLink";
import {
  CITATION_SCHEME,
  citationMarkerFromHref,
  toCitationLinks,
} from "../lib/citationMarkdown";
import { tidyMarkdown } from "../lib/markdownTidy";
import { formatFromFilename, usePreview } from "../lib/previewContext";
import { CodeBlock } from "./CodeBlock";

/**
 * 回答正文的 Markdown 渲染。
 *
 * 引用标记先由 toCitationLinks 改写成 [编号](cite:编号)，再由 a 组件拦下 cite: 协议，
 * 渲染成跳转原文的引用徽章；代码块交给 CodeBlock 提供语言标签与复制按钮。
 */
const LINK_CLASS =
  "font-medium text-accent underline decoration-accent/40 underline-offset-2 transition hover:decoration-accent";
// 引用做成小徽章：只显示数字，底色比正文浅一档，不打断阅读节奏。
const CITATION_BADGE =
  "mx-0.5 inline-flex h-[1.35em] min-w-[1.35em] -translate-y-px items-center justify-center rounded-[4px] bg-accent-wash px-1 align-baseline text-[0.72em] font-semibold leading-none text-accent no-underline transition hover:bg-accent hover:text-white";

/**
 * react-markdown 默认只放行 http/https/mailto/tel 和相对地址，
 * 自定义的 cite: 协议会被洗成空串，这里单独放行，其余仍走默认校验。
 */
function urlTransform(url: string): string {
  return url.startsWith(CITATION_SCHEME) ? url : defaultUrlTransform(url);
}

function hastText(node: ElementContent): string {
  if (node.type === "text") {
    return node.value;
  }
  if (node.type === "element") {
    return node.children.map(hastText).join("");
  }
  return "";
}

/** 从 pre > code 节点里取出语言标记和纯文本，供代码卡片与复制按钮使用。 */
function codeBlockMeta(node: Element | undefined): { language: string; code: string } {
  const codeNode = node?.children?.find(
    (child): child is Element => child.type === "element",
  );
  if (!codeNode) {
    return { language: "", code: "" };
  }
  const raw: unknown = codeNode.properties?.className;
  const classes = Array.isArray(raw)
    ? raw.map((item: unknown) => String(item))
    : typeof raw === "string"
      ? raw.split(/\s+/)
      : [];
  const language =
    classes.find((item) => item.startsWith("language-"))?.slice("language-".length) ?? "";
  return { language, code: hastText(codeNode).replace(/\n+$/, "") };
}

export function MarkdownAnswer({
  content,
  citations,
}: {
  content: string;
  citations: Citation[];
}) {
  const { openPreview } = usePreview();
  // 先修中文写法里不成立的标记，再把 [1] 改写成引用链接，避免互相干扰。
  const source = useMemo(() => toCitationLinks(tidyMarkdown(content)), [content]);

  const components = useMemo<Components>(() => {
    const byMarker = new Map(
      citations.map((citation) => [citation.marker_index, citation]),
    );

    return {
      h1: ({ children }) => (
        <h1 className="mb-2 mt-5 text-lg font-semibold text-ink first:mt-0">
          {children}
        </h1>
      ),
      h2: ({ children }) => (
        <h2 className="mb-2 mt-5 border-b border-ink-line pb-1 text-base font-semibold text-ink first:mt-0">
          {children}
        </h2>
      ),
      h3: ({ children }) => (
        <h3 className="mb-1.5 mt-4 text-sm font-semibold text-ink first:mt-0">
          {children}
        </h3>
      ),
      h4: ({ children }) => (
        <h4 className="mb-1.5 mt-3 text-sm font-semibold text-ink-soft first:mt-0">
          {children}
        </h4>
      ),
      p: ({ children }) => (
        <p className="my-2 leading-7 first:mt-0 last:mb-0">{children}</p>
      ),
      ul: ({ children }) => (
        <ul className="my-2 list-disc space-y-1 pl-5 marker:text-ink-mute">{children}</ul>
      ),
      ol: ({ children }) => (
        <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-ink-mute">
          {children}
        </ol>
      ),
      li: ({ children }) => (
        <li className="pl-0.5 leading-7 [&>ol]:my-1 [&>p]:my-0 [&>ul]:my-1">
          {children}
        </li>
      ),
      strong: ({ children }) => (
        <strong className="font-semibold text-ink">{children}</strong>
      ),
      em: ({ children }) => <em className="italic">{children}</em>,
      del: ({ children }) => <del className="text-ink-mute line-through">{children}</del>,
      blockquote: ({ children }) => (
        <blockquote className="my-3 border-l-2 border-accent/30 pl-3 text-ink-soft">
          {children}
        </blockquote>
      ),
      hr: () => <hr className="my-4 border-ink-line" />,
      pre: ({ node, children }) => {
        const { language, code } = codeBlockMeta(node);
        return (
          <CodeBlock language={language} code={code}>
            {children}
          </CodeBlock>
        );
      },
      code: ({ className, children }) => {
        // 围栏代码块由 CodeBlock 提供外壳，这里保留 hljs 的类名让高亮生效。
        if (
          typeof className === "string" &&
          (className.includes("language-") || className.includes("hljs"))
        ) {
          return <code className={className}>{children}</code>;
        }
        return (
          <code className="rounded bg-paper-deep px-1 py-0.5 font-mono text-[0.92em] text-ink">
            {children}
          </code>
        );
      },
      table: ({ children }) => (
        <div className="my-3 overflow-x-auto rounded-xl border border-ink-line">
          <table className="w-full border-collapse text-left text-xs">{children}</table>
        </div>
      ),
      thead: ({ children }) => (
        <thead className="bg-paper-deep text-ink">{children}</thead>
      ),
      th: ({ children }) => (
        <th className="border-b border-ink-line px-3 py-2 font-semibold">{children}</th>
      ),
      td: ({ children }) => (
        <td className="border-b border-ink-line px-3 py-2 align-top text-ink-soft">
          {children}
        </td>
      ),
      a: ({ href, children }) => {
        const marker = typeof href === "string" ? citationMarkerFromHref(href) : null;
        if (marker !== null) {
          const citation = byMarker.get(marker);
          const documentId = citation?.document_id;
          const label = citation
            ? `引用 ${marker}：${citation.document_name} ${citation.source_location}`
            : `引用 ${marker}`;
          if (!citation || !documentId) {
            return (
              <span className={CITATION_BADGE} title={label}>
                {children}
              </span>
            );
          }
          // 点编号直接在右侧打开原文：Office 文件用原文件链接只会触发下载。
          return (
            <button
              type="button"
              onClick={() =>
                openPreview({
                  documentId,
                  filename: citation.document_name,
                  format: formatFromFilename(citation.document_name),
                  page: citationPage(citation.source_location),
                  chunkId: citation.chunk_id,
                  highlightText: citation.quote_snapshot,
                  location: citation.source_location,
                })
              }
              title={label}
              aria-label={label}
              className={CITATION_BADGE}
            >
              {children}
            </button>
          );
        }
        return (
          <a href={href} target="_blank" rel="noreferrer" className={LINK_CLASS}>
            {children}
          </a>
        );
      },
    };
  }, [citations, openPreview]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={components}
      urlTransform={urlTransform}
    >
      {source}
    </ReactMarkdown>
  );
}
