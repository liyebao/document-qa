import { useMemo } from "react";
import type { Citation } from "../api/types";
import { citationPage } from "../lib/citationLink";
import { formatFromFilename, usePreview } from "../lib/previewContext";

interface FileGroup {
  key: string;
  documentName: string;
  format: string;
  citations: Citation[];
}

/** 同一份文件的多个引用合并成一组，避免来源列表里重复出现同一条文件名。 */
function groupByDocument(citations: Citation[]): FileGroup[] {
  const groups = new Map<string, FileGroup>();
  for (const citation of citations) {
    const key = citation.document_id ?? `name:${citation.document_name}`;
    const existing = groups.get(key);
    if (existing) {
      existing.citations.push(citation);
      continue;
    }
    groups.set(key, {
      key,
      documentName: citation.document_name,
      format: formatFromFilename(citation.document_name),
      citations: [citation],
    });
  }
  for (const group of groups.values()) {
    group.citations.sort((left, right) => left.marker_index - right.marker_index);
  }
  return [...groups.values()];
}

export function CitationList({ citations }: { citations: Citation[] }) {
  const { openPreview } = usePreview();
  const groups = useMemo(() => groupByDocument(citations), [citations]);

  if (citations.length === 0) {
    return null;
  }

  function openSource(citation: Citation) {
    if (!citation.document_id) {
      return;
    }
    openPreview({
      documentId: citation.document_id,
      filename: citation.document_name,
      format: formatFromFilename(citation.document_name),
      page: citationPage(citation.source_location),
      chunkId: citation.chunk_id,
      highlightText: citation.quote_snapshot,
      location: citation.source_location,
    });
  }

  return (
    <details className="group mt-4">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-2 text-xs font-semibold text-ink-mute transition hover:text-accent [&::-webkit-details-marker]:hidden">
        <span className="text-ink-soft">引用来源</span>
        <span className="font-normal">
          {groups.length} 个文件 · {citations.length} 条引用
        </span>
        <span className="text-accent group-open:hidden">展开</span>
        <span className="hidden group-open:inline">收起</span>
      </summary>

      <div className="mt-2 space-y-2">
        {groups.map((group) => (
          <div
            key={group.key}
            className="rounded-xl border border-ink-line bg-paper-card px-3 py-2"
          >
            <p className="truncate text-xs font-medium text-ink">{group.documentName}</p>
            <ul className="mt-1.5 space-y-1">
              {group.citations.map((citation) => (
                <li key={citation.id}>
                  <button
                    type="button"
                    onClick={() => openSource(citation)}
                    title="在右侧查看原文并定位到这一段"
                    className="flex w-full items-baseline gap-2 rounded-md px-1 py-1 text-left text-xs text-ink-soft transition hover:bg-white hover:text-accent"
                  >
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent-wash text-[11px] font-semibold text-accent">
                      {citation.marker_index}
                    </span>
                    <span className="shrink-0 text-ink-mute">
                      {citation.source_location}
                    </span>
                    <span className="min-w-0 line-clamp-1 text-ink-mute">
                      {citation.quote_snapshot}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}
