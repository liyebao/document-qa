import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createCollection, deleteCollection, listCollections } from "../api/collections";
import { errorMessage } from "../api/client";
import type { CollectionSummary } from "../api/types";
import { notifyConversationsChanged } from "../app/recent";

export function CollectionsPage() {
  const [items, setItems] = useState<CollectionSummary[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        <div className="rounded-xl bg-white px-4 py-3 text-sm shadow-card">
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

      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">所有资料集</h2>
        <span className="text-sm text-ink-mute">{items.length} 个</span>
      </div>

      {loading ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div
              key={item}
              className="h-40 animate-pulse rounded-2xl bg-white shadow-card"
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
          {items.map((item) => (
            <li
              key={item.id}
              className="group relative flex min-h-48 flex-col rounded-2xl border border-ink-line bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-lift"
            >
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
                <h3 className="truncate text-lg font-semibold text-ink group-hover:text-accent">
                  {item.name}
                </h3>
                <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-ink-soft">
                  {item.embedding_model
                    ? `索引模型：${item.embedding_model}`
                    : "添加资料后建立检索索引"}
                </p>
              </Link>
              <div className="mt-auto flex items-center justify-between border-t border-ink-line pt-4 text-xs text-ink-mute">
                <span>{item.document_count} 份文件</span>
                <span>{new Date(item.created_at).toLocaleDateString("zh-CN")}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
