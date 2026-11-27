import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createCollection, deleteCollection, listCollections } from "../api/collections";
import { errorMessage } from "../api/client";
import type { CollectionSummary } from "../api/types";
import { notifyConversationsChanged } from "../app/recent";

/** 「所有资料集」标题右侧的三横：进入多选模式后逐项勾选并批量删除。 */
function SelectIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

export function CollectionsPage() {
  const [items, setItems] = useState<CollectionSummary[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 多选只作用于「所有资料集」列表；后端没有批量删除接口，删除时并行调用单条删除再汇总。
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setItems(await listCollections());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setBusy(true);
    try {
      await createCollection(name.trim());
      setName("");
      await load();
      notifyConversationsChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(item: CollectionSummary) {
    if (!window.confirm(`确认删除资料集“${item.name}”及其中的文件和会话吗？`)) {
      return;
    }
    try {
      await deleteCollection(item.id);
      await load();
      notifyConversationsChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const allSelected = items.length > 0 && selectedIds.length === items.length;

  function enterSelectMode() {
    setSelectedIds([]);
    setSelectMode(true);
  }

  function exitSelectMode() {
    setSelectedIds([]);
    setSelectMode(false);
  }

  function toggleSelected(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function handleBatchDelete() {
    const targets = items.filter((item) => selectedIds.includes(item.id));
    if (targets.length === 0 || deleting) {
      return;
    }
    const names = targets.map((item) => `“${item.name}”`).join("、");
    if (
      !window.confirm(
        `确认删除选中的 ${targets.length} 个资料集及其中的文件和会话吗？\n${names}`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const results = await Promise.allSettled(targets.map((item) => deleteCollection(item.id)));
      const failedIds = targets
        .filter((_, index) => results[index].status === "rejected")
        .map((item) => item.id);
      await load();
      notifyConversationsChanged();
      if (failedIds.length > 0) {
        const reasons = results
          .map((result) =>
            result.status === "rejected" ? errorMessage(result.reason) : null,
          )
          .filter((reason): reason is string => reason !== null);
        setSelectedIds(failedIds);
        setError(`${failedIds.length} 个资料集删除失败，可再试一次：${reasons.join("；")}`);
      } else {
        exitSelectMode();
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl animate-rise">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="text-sm font-semibold text-accent">个人知识库</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
            我的资料集
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-soft">
            按主题整理文件，在资料范围内提问，并通过引用回到原文核对答案。
          </p>
        </div>
        <div className="rounded-xl bg-paper-card px-4 py-3 text-sm shadow-card">
          <span className="text-2xl font-bold text-ink">{items.length}</span>
          <span className="ml-2 text-ink-mute">个资料集</span>
        </div>
      </div>

      <form
        onSubmit={handleCreate}
        className="surface mt-8 flex flex-col gap-3 p-4 sm:flex-row"
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={100}
          placeholder="给新资料集起个名字，例如：毕业设计调研"
          aria-label="新资料集名称"
          className="field flex-1"
        />
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="btn-primary shrink-0 px-5"
        >
          {busy ? "正在创建…" : "＋ 新建资料集"}
        </button>
      </form>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm leading-relaxed text-vermilion"
        >
          {error}
        </p>
      )}

      <div className="mt-10 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">所有资料集</h2>
        <div className="flex items-center gap-1.5">
          {selectMode ? (
            <>
              <span className="text-sm tabular-nums text-ink-mute" aria-live="polite">
                已选 {selectedIds.length}
              </span>
              <button
                type="button"
                onClick={() => setSelectedIds(allSelected ? [] : items.map((item) => item.id))}
                className="row-action"
              >
                {allSelected ? "取消全选" : "全选"}
              </button>
              <button type="button" onClick={exitSelectMode} className="row-action">
                完成
              </button>
            </>
          ) : (
            <>
              <span className="text-sm text-ink-mute">{items.length} 个</span>
              {items.length > 0 && (
                <button
                  type="button"
                  onClick={enterSelectMode}
                  aria-label="多选资料集"
                  title="多选资料集"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-mute transition hover:bg-accent-wash hover:text-accent"
                >
                  <SelectIcon />
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {selectMode && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-2.5 text-sm leading-6 text-vermilion">
          <span>删除资料集会一并移除其中的文件与会话，此操作不可撤销。</span>
          <button
            type="button"
            onClick={() => void handleBatchDelete()}
            disabled={selectedIds.length === 0 || deleting}
            className="btn bg-vermilion text-paper hover:bg-vermilion-dark disabled:bg-paper-deep disabled:text-ink-mute"
          >
            {deleting ? "删除中…" : `删除选中（${selectedIds.length}）`}
          </button>
        </div>
      )}

      {loading ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-40 animate-pulse rounded-2xl bg-paper-card shadow-card"
            />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="surface mt-4 px-6 py-16 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-wash text-xl font-bold text-accent">
            ＋
          </div>
          <h3 className="mt-4 text-base font-semibold text-ink">从一个资料集开始</h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-ink-soft">
            创建后即可上传 PDF、Word、Markdown 等资料，系统会为它们建立可检索的索引。
          </p>
        </div>
      ) : (
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            const checked = selectedIds.includes(item.id);
            const cardClass = `group relative flex min-h-48 flex-col rounded-2xl border p-5 shadow-card transition duration-200 ${
              selectMode
                ? checked
                  ? "cursor-pointer border-accent bg-accent-wash/40 shadow-lift"
                  : "cursor-pointer border-ink-line bg-paper-card hover:border-accent/30"
                : "border-ink-line bg-paper-card hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-lift"
            }`;
            const meta = (
              <div className="mt-auto flex items-center justify-between border-t border-ink-line pt-4 text-xs text-ink-mute">
                <span>{item.document_count} 份文件</span>
                <span>{new Date(item.created_at).toLocaleDateString("zh-CN")}</span>
              </div>
            );
            const detail = (
              <>
                <h3 className="truncate text-lg font-semibold text-ink group-hover:text-accent">
                  {item.name}
                </h3>
                <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-ink-soft">
                  {item.embedding_model
                    ? `索引模型：${item.embedding_model}`
                    : "添加资料后建立检索索引"}
                </p>
              </>
            );

            if (selectMode) {
              return (
                <li key={item.id}>
                  <label className={cardClass}>
                    <div className="flex items-start justify-between gap-3">
                      <div
                        className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-wash text-lg font-bold text-accent"
                        aria-hidden="true"
                      >
                        文
                      </div>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelected(item.id)}
                        aria-label={`选择资料集 ${item.name}`}
                        className="checkbox mt-1 h-5 w-5"
                      />
                    </div>
                    <div className="mt-4">{detail}</div>
                    {meta}
                  </label>
                </li>
              );
            }

            return (
              <li key={item.id} className={cardClass}>
                <div className="flex items-start justify-between gap-3">
                  <div
                    className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-wash text-lg font-bold text-accent"
                    aria-hidden="true"
                  >
                    文
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDelete(item)}
                    aria-label={`删除资料集 ${item.name}`}
                    className="inline-flex min-h-11 items-center rounded-lg px-2.5 text-xs font-medium text-ink-mute transition hover:bg-vermilion-wash hover:text-vermilion"
                  >
                    删除
                  </button>
                </div>
                <Link
                  to={`/collections/${item.id}`}
                  className="mt-4 rounded-md focus-visible:outline-accent"
                >
                  {detail}
                </Link>
                {meta}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
