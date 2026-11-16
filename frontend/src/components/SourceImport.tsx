import { FormEvent, useState } from "react";

interface Props {
  busy: boolean;
  onCreateText: (title: string, content: string) => Promise<void>;
  onImportUrl: (url: string) => Promise<void>;
}

type Mode = "text" | "url";

const inputClass =
  "w-full rounded-lg border border-ink-line bg-white px-3 py-2.5 text-sm text-ink outline-none transition focus:border-accent focus:ring-4 focus:ring-accent/10";

export function SourceImport({ busy, onCreateText, onImportUrl }: Props) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      if (mode === "text") {
        await onCreateText(title.trim(), content.trim());
        setTitle("");
        setContent("");
      } else if (mode === "url") {
        await onImportUrl(url.trim());
        setUrl("");
      }
    } catch {
      // 错误信息由父组件展示，保留输入便于直接重试。
    }
  }

  function toggle(next: Mode) {
    setMode((current) => (current === next ? null : next));
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-mute">
        <span className="mr-1 font-medium">还可以添加</span>
        <button
          type="button"
          onClick={() => toggle("text")}
          className="rounded-lg bg-paper px-3 py-2 font-medium text-ink-soft transition hover:bg-accent-wash hover:text-accent"
        >
          粘贴文本
        </button>
        <button
          type="button"
          onClick={() => toggle("url")}
          className="rounded-lg bg-paper px-3 py-2 font-medium text-ink-soft transition hover:bg-accent-wash hover:text-accent"
        >
          导入链接
        </button>
      </div>

      {mode && (
        <form
          onSubmit={(event) => void handleSubmit(event)}
          className="mt-3 space-y-3 rounded-xl border border-ink-line bg-paper p-4"
        >
          {mode === "text" ? (
            <>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="标题，例如：项目会议纪要"
                maxLength={200}
                required
                className={inputClass}
              />
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="粘贴需要入库的文本，空行分段"
                rows={5}
                maxLength={200000}
                required
                className={`${inputClass} resize-y leading-6`}
              />
            </>
          ) : (
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com/article"
              maxLength={2048}
              required
              className={inputClass}
            />
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="btn-accent h-8 shrink-0 px-3 text-[11px]"
            >
              {busy ? "处理中…" : mode === "text" ? "文本入库" : "抓取并入库"}
            </button>
            <button
              type="button"
              onClick={() => setMode(null)}
              className="rounded-lg px-3 py-2 text-xs font-medium text-ink-mute transition hover:bg-white hover:text-ink"
            >
              取消
            </button>
          </div>

          {mode === "url" && (
            <p className="text-xs leading-5 text-ink-mute">
              仅抓取公开网页正文，内网地址和需要登录的页面会被拒绝。
            </p>
          )}
        </form>
      )}
    </div>
  );
}
