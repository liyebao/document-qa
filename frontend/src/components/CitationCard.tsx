import { useState } from "react";
import { errorMessage } from "../api/client";
import { getChunkContext } from "../api/documents";
import type { ChunkContext, Citation } from "../api/types";
import { citationFileUrl } from "../lib/citationLink";

function ContextBlock({
  label,
  snippet,
}: {
  label: string;
  snippet: { source_location: string; text: string };
}) {
  return (
    <div className="mb-2 rounded-lg bg-paper p-3">
      <span className="text-xs font-medium text-ink-mute">
        {label} · {snippet.source_location}
      </span>
      <p className="mt-1 whitespace-pre-wrap break-words">{snippet.text}</p>
    </div>
  );
}

export function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const fileUrl = citationFileUrl(citation);
  const [context, setContext] = useState<ChunkContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);

  async function loadContext() {
    if (context || contextLoading || !citation.document_id || !citation.chunk_id) {
      return;
    }
    setContextLoading(true);
    setContextError(null);
    try {
      setContext(await getChunkContext(citation.document_id, citation.chunk_id));
    } catch (err) {
      setContextError(errorMessage(err));
    } finally {
      setContextLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-ink-line bg-white px-3 py-2 transition-colors duration-200 hover:border-accent/30">
      <div className="flex items-baseline gap-2 text-sm text-ink-soft">
        {fileUrl ? (
          <a
            href={fileUrl}
            target="_blank"
            rel="noreferrer"
            title="打开原文件"
            className="flex min-w-0 flex-1 items-baseline gap-2 transition hover:text-accent"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-wash text-xs font-semibold text-accent">
              {index}
            </span>
            <span className="truncate font-medium">{citation.document_name}</span>
            <span className="shrink-0 text-xs text-ink-mute">
              {citation.source_location}
            </span>
            <span className="ml-auto shrink-0 text-xs font-medium text-accent">
              打开原文 ↗
            </span>
          </a>
        ) : (
          <span className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-wash text-xs font-semibold text-accent">
              {index}
            </span>
            <span className="truncate font-medium">{citation.document_name}</span>
            <span className="shrink-0 text-xs text-ink-mute">
              {citation.source_location}
            </span>
          </span>
        )}
      </div>

      <details
        className="group pt-2"
        onToggle={(event) => {
          if (event.currentTarget.open) {
            void loadContext();
          }
        }}
      >
        <summary className="flex w-fit cursor-pointer list-none items-center gap-1 text-xs font-medium text-ink-mute transition hover:text-accent [&::-webkit-details-marker]:hidden">
          <span className="group-open:hidden">查看引用片段与上下文</span>
          <span className="hidden group-open:inline">收起引用片段</span>
        </summary>
        <div className="pt-3 pr-1 text-sm leading-6 text-ink-mute">
          {context?.previous && (
            <ContextBlock label="上一段" snippet={context.previous} />
          )}
          <p className="whitespace-pre-wrap break-words text-ink-soft">
            {citation.quote_snapshot}
          </p>
          {context?.next && <ContextBlock label="下一段" snippet={context.next} />}
          {contextLoading && (
            <p className="mt-2 text-xs text-ink-mute">正在读取上下文…</p>
          )}
          {contextError && (
            <p role="alert" className="mt-2 text-xs text-vermilion">
              {contextError}
            </p>
          )}
        </div>
      </details>
    </div>
  );
}
