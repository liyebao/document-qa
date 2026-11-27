import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createConversation } from "../api/collections";
import { errorMessage } from "../api/client";
import type { CollectionSummary } from "../api/types";
import { notifyConversationsChanged } from "./recent";
import { useFocusTrap } from "./useFocusTrap";

interface Props {
  open: boolean;
  collections: CollectionSummary[];
  loading: boolean;
  /** 取资料集失败时的原因；有值时显示错误态，而不是误显示「还没有资料集」。 */
  error?: string | null;
  onClose: () => void;
}

function SearchIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m16.5 16.5 4 4" />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-3.5 w-3.5"
    >
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

/**
 * “新建对话”先选资料集：会话必须挂在资料集下，直接跳走会让用户不知道
 * 回答到底基于哪些文件。选择后创建会话并进入对话页。
 */
export function NewConversationDialog({ open, collections, loading, error = null, onClose }: Props) {
  const navigate = useNavigate();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const firstOptionRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useFocusTrap(panelRef, open);

  useEffect(() => {
    if (!open) {
      return;
    }
    setFailure(null);
    // 每次打开都从完整列表开始，避免上次的搜索词把选项藏起来。
    setQuery("");
    const timer = window.setTimeout(() => firstOptionRef.current?.focus(), 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  // 只按资料集名称过滤：这个弹窗的用途是「选一个资料集」，数量多时靠名字最快。
  const keyword = query.trim().toLowerCase();
  const filtered = keyword
    ? collections.filter((collection) =>
        collection.name.toLowerCase().includes(keyword),
      )
    : collections;

  const clearSearch = () => {
    setQuery("");
    searchRef.current?.focus();
  };

  async function handlePick(collection: CollectionSummary) {
    setBusyId(collection.id);
    setFailure(null);
    try {
      const conversation = await createConversation(collection.id);
      notifyConversationsChanged();
      onClose();
      navigate(`/conversations/${conversation.id}`);
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-4 sm:items-center">
      <button
        type="button"
        aria-label="关闭新建对话"
        onClick={onClose}
        className="absolute inset-0 animate-fade cursor-default bg-black/40 backdrop-blur-sm"
      />

      <div
        role="dialog"
        ref={panelRef}
        aria-modal="true"
        aria-labelledby="new-conversation-title"
        className="surface relative flex max-h-[85dvh] w-full max-w-md animate-rise flex-col overflow-hidden p-0"
      >
        <div className="shrink-0 border-b border-ink-line px-5 py-4">
          <h2 id="new-conversation-title" className="text-base font-semibold text-ink">
            新建对话
          </h2>
          <p className="mt-1 text-xs leading-5 text-ink-mute">
            选择一个资料集，回答只会引用该资料集里已建索引的文件。
          </p>
        </div>

        {!loading && !error && collections.length > 0 ? (
          <div className="shrink-0 border-b border-ink-line px-5 py-3">
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-mute">
                <SearchIcon />
              </span>
              <input
                ref={searchRef}
                id="new-conversation-search"
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  // 有搜索词时 Esc 先清空，再按一次才关闭弹窗。
                  if (event.key === "Escape" && query) {
                    event.stopPropagation();
                    clearSearch();
                  }
                }}
                placeholder="搜索资料集名称"
                aria-label="搜索资料集"
                aria-describedby="new-conversation-search-hint"
                autoComplete="off"
                className="field h-10 py-0 pl-9 pr-9 text-sm"
              />
              {query ? (
                <button
                  type="button"
                  onClick={clearSearch}
                  aria-label="清空搜索"
                  className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink-mute transition hover:bg-paper-deep hover:text-ink"
                >
                  <ClearIcon />
                </button>
              ) : null}
            </div>
            <p
              id="new-conversation-search-hint"
              className="mt-1.5 text-xs tabular-nums text-ink-mute"
              aria-live="polite"
            >
              {keyword
                ? `找到 ${filtered.length} 个资料集`
                : `共 ${collections.length} 个资料集`}
            </p>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="space-y-2 p-2">
              {[0, 1, 2].map((index) => (
                <div
                  key={index}
                  className="h-14 animate-pulse rounded-xl bg-paper-deep"
                />
              ))}
            </div>
          ) : error ? (
            <div className="px-4 py-10 text-center">
              <p className="text-sm font-semibold text-ink">资料集加载失败</p>
              <p className="mt-2 text-sm leading-6 text-ink-soft">{error}</p>
              <p className="mt-2 text-xs leading-5 text-ink-mute">
                请关闭后重试，或检查后端服务是否在运行。
              </p>
            </div>
          ) : collections.length === 0 ? (
            <div className="px-4 py-10 text-center">
              <p className="text-sm font-semibold text-ink">还没有资料集</p>
              <p className="mt-2 text-sm leading-6 text-ink-soft">
                先创建一个资料集并上传文件，然后就可以围绕它提问。
              </p>
              <Link
                to="/"
                onClick={onClose}
                className="btn-primary mt-5 min-h-10 px-4 text-xs"
              >
                去新建资料集
              </Link>
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-10 text-center">
              <p className="text-sm font-semibold text-ink">没有匹配的资料集</p>
              <p className="mt-2 text-sm leading-6 text-ink-soft">
                「{query.trim()}」没有找到对应的资料集，换个关键词或清空搜索试试。
              </p>
              <button
                type="button"
                onClick={clearSearch}
                className="btn btn-ghost mt-5 min-h-10 px-4 text-xs"
              >
                清空搜索
              </button>
            </div>
          ) : (
            <ul className="space-y-1">
              {filtered.map((collection, index) => (
                <li key={collection.id}>
                  <button
                    ref={index === 0 ? firstOptionRef : undefined}
                    type="button"
                    disabled={busyId !== null}
                    onClick={() => void handlePick(collection)}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition duration-200 ease-out hover:bg-accent-wash disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span
                      aria-hidden="true"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-paper text-sm font-bold text-accent"
                    >
                      文
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink">
                        {collection.name}
                      </span>
                      <span className="mt-0.5 block text-xs text-ink-mute">
                        {collection.document_count} 份文件
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-medium text-accent">
                      {busyId === collection.id ? "创建中…" : "开始 →"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {failure && (
            <p
              role="alert"
              className="mx-2 mt-2 rounded-lg bg-vermilion-wash px-3 py-2 text-xs leading-5 text-vermilion"
            >
              {failure}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-ink-line px-5 py-3">
          <span className="text-xs text-ink-mute">会话可以随时在资料集里删除</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-xs font-medium text-ink-soft transition hover:bg-paper hover:text-ink"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
