import type { RetrievalTraceData } from "../api/types";

/** 回答上方折叠展示的检索过程：实际查了什么、看了哪些资料的哪一段。 */
export function RetrievalTrace({ trace }: { trace: RetrievalTraceData }) {
  // 老会话的消息只有空的 retrieval_trace 对象，字段可能整体缺失。
  const queries = trace.queries ?? [];
  const documents = trace.documents ?? [];
  const queryCount = queries.length;
  const documentCount = documents.length;
  // 旧消息只有 cross_doc_chunks，新消息写 reference_chunks。
  const filled = trace.reference_chunks ?? trace.cross_doc_chunks ?? 0;
  if (queryCount === 0 && documentCount === 0) {
    return null;
  }

  return (
    <details className="mb-3 rounded-xl border border-ink-line bg-paper-card/60 px-3 py-2 text-xs">
      <summary className="cursor-pointer list-none text-ink-mute transition hover:text-accent">
        检索过程 · {trace.searches ?? 0} 次检索
        {(trace.expanded ?? 0) > 0 ? ` · ${trace.expanded} 次扩展` : ""}
        {(trace.full_scan_chunks ?? 0) > 0
          ? ` · 已通读 ${trace.full_scan_chunks} 处原文`
          : ""}
        {filled > 0 ? ` · 按编号补证 ${filled} 处` : ""}
        {" · "}{documentCount} 处依据
        <span className="ml-1">▾</span>
      </summary>
      {queryCount > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="shrink-0 text-ink-mute">已检索</span>
          {queries.map((query) => (
            <span
              key={query}
              className="rounded-md bg-accent-wash px-2 py-0.5 text-accent"
            >
              {query}
            </span>
          ))}
        </div>
      )}
      {documentCount > 0 && (
        <div className="mt-2 space-y-1">
          <span className="text-ink-mute">已浏览</span>
          <ul className="space-y-0.5">
            {documents.map((document) => (
              <li key={`${document.name}-${document.marker}`} className="text-ink-soft">
                <span className="mr-1 text-accent">[{document.marker}]</span>
                {document.name}
                {document.location ? (
                  <span className="text-ink-mute"> · {document.location}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}
