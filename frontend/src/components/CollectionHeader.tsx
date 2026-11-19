import { Link } from "react-router-dom";
import type { CollectionOut } from "../api/types";

interface Props {
  collection: CollectionOut;
  documentCount: number;
  reindexing: boolean;
  onReindex: () => void;
  onRename: () => void;
}

export function CollectionHeader({
  collection,
  documentCount,
  reindexing,
  onReindex,
  onRename,
}: Props) {
  return (
    <div className="surface p-5 sm:p-6">
      <Link
        to="/"
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-mute transition hover:text-accent"
      >
        ← 全部资料集
      </Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            {collection.name}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-mute">
            <span className="rounded-full bg-paper px-3 py-1.5">
              {documentCount} 份文件
            </span>
            <span>
              {collection.embedding_model
                ? `索引模型 ${collection.embedding_model} · ${collection.embedding_dimension} 维`
                : "添加首份文件后自动建立索引"}
            </span>
            <span className="rounded-full bg-paper px-3 py-1.5">
              索引 v{collection.index_version}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {documentCount > 0 && (
            <button
              type="button"
              onClick={onReindex}
              disabled={reindexing}
              className="btn-ghost min-h-11 px-3 text-xs"
            >
              {reindexing ? "重建中…" : "重建索引 ↻"}
            </button>
          )}
          <button
            type="button"
            onClick={onRename}
            className="btn-ghost min-h-11 px-3 text-xs"
          >
            重命名 ↗
          </button>
        </div>
      </div>
    </div>
  );
}
