import type { ReactNode } from "react";
import { useCopyState } from "../lib/clipboard";

/**
 * 代码块卡片：语言标签 + 复制按钮 + 横向滚动。
 *
 * 高亮由 rehype-highlight 在 markdown 解析阶段完成，这里只负责外壳，
 * children 是已经带 hljs class 的 <code> 元素。
 */
export function CodeBlock({
  language,
  code,
  children,
}: {
  language: string;
  code: string;
  children: ReactNode;
}) {
  const { copyState, copy } = useCopyState();

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-ink-line bg-paper-sunken">
      <div className="flex items-center justify-between border-b border-ink-line bg-paper-deep/70 px-3 py-1.5">
        <span className="font-mono text-xs tracking-wide text-ink-mute">
          {language || "text"}
        </span>
        <button
          type="button"
          onClick={() => void copy(code)}
          aria-live="polite"
          className={`rounded-md px-1.5 py-0.5 text-xs font-medium transition hover:bg-paper-card ${
            copyState === "done"
              ? "text-jade"
              : copyState === "error"
                ? "text-vermilion"
                : "text-ink-mute hover:text-ink"
          }`}
        >
          {copyState === "done" ? "已复制" : copyState === "error" ? "复制失败" : "复制"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-3 font-mono text-xs leading-6 text-ink-soft">
        {children}
      </pre>
    </div>
  );
}
