import { useCallback, useEffect, useRef, useState } from "react";
import { documentFileUrl, documentRenderUrl } from "../api/documents";
import type { PreviewRequest } from "../lib/previewContext";

// 浏览器能原生渲染的格式：直接内嵌原文件，所见即原文件。
const NATIVE_PREVIEW = new Set(["pdf", "png", "jpg", "jpeg", "webp", "gif", "bmp"]);

/** 按句末标点切分，用短句做种子更容易在段落里命中。 */
function seedPhrases(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) {
    return [];
  }
  const parts: string[] = [];
  let buffer = "";
  for (const char of trimmed) {
    buffer += char;
    if ("。！？；\n".includes(char)) {
      const sentence = buffer.trim();
      if (sentence.length >= 10) {
        parts.push(sentence);
      }
      buffer = "";
    }
  }
  const tail = buffer.trim();
  if (tail.length >= 10) {
    parts.push(tail);
  }
  return [trimmed, ...parts];
}

/**
 * 在预览文档里定位引用文字并高亮。
 *
 * 这里只处理同一个文本节点内的匹配：渲染出来的每个段落是独立元素，
 * 引用片段通常完整落在一段之内；跨段匹配交给底部"引用片段"兜底。
 */
function highlightInFrame(frame: HTMLIFrameElement, needle: string): boolean {
  const doc = frame.contentDocument;
  if (!doc || !doc.body) {
    return false;
  }
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    if (node.nodeValue && node.nodeValue.trim()) {
      nodes.push(node);
    }
  }

  for (const phrase of seedPhrases(needle)) {
    for (const node of nodes) {
      const value = node.nodeValue ?? "";
      const index = value.indexOf(phrase);
      if (index < 0) {
        continue;
      }
      const range = doc.createRange();
      range.setStart(node, index);
      range.setEnd(node, index + phrase.length);
      const mark = doc.createElement("mark");
      mark.className = "__hit";
      range.surroundContents(mark);
      mark.scrollIntoView({ block: "center" });
      return true;
    }
  }
  return false;
}

interface Props {
  request: PreviewRequest | null;
  onClose: () => void;
}

export function DocumentPreviewPanel({ request, onClose }: Props) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const [located, setLocated] = useState(true);

  const native = request ? NATIVE_PREVIEW.has(request.format) : false;
  const src = request
    ? native
      ? documentFileUrl(request.documentId, request.page ?? null)
      : documentRenderUrl(request.documentId)
    : "";

  useEffect(() => {
    setLocated(true);
  }, [request]);

  useEffect(() => {
    if (!request) {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [request, onClose]);

  const handleLoad = useCallback(() => {
    const frame = frameRef.current;
    if (!frame || !request) {
      return;
    }
    // PDF 与图片由浏览器阅读器渲染，脚本无法进入，只能靠 #page 定位。
    if (native || !request.highlightText) {
      return;
    }
    try {
      setLocated(highlightInFrame(frame, request.highlightText));
    } catch {
      // 跨源或文档结构异常时放弃高亮，不影响阅读原文。
      setLocated(false);
    }
  }, [native, request]);

  if (!request) {
    return null;
  }

  return (
    <>
      {/* 窄屏没有并排空间，退化成全屏浮层；md 以上面板直接参与布局，不再遮挡对话。 */}
      <button
        type="button"
        aria-label="关闭预览"
        onClick={onClose}
        className="fixed inset-0 z-40 cursor-default bg-ink/25 md:hidden"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${request.filename} 预览`}
        // 宽度由 PreviewProvider 的 --preview-width 控制（分隔条可拖），
        // 再叠 min/max 兜底，防止拖到任意一边看不见。
        className="fixed inset-0 z-50 flex w-full flex-col bg-white md:static md:z-auto md:w-[var(--preview-width)] md:min-w-[320px] md:max-w-[72%] md:shrink-0 md:rounded-2xl md:border md:border-ink-line md:shadow-card"
      >
        <header className="flex shrink-0 items-start gap-3 border-b border-ink-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{request.filename}</p>
            <p className="mt-0.5 text-xs text-ink-mute">
              {request.location || "原文件预览"}
              {!located ? " · 未能在页面中定位到引用位置" : ""}
            </p>
          </div>
          <a
            href={src}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-xs font-medium text-accent transition hover:text-accent-dark"
          >
            新窗口 ↗
          </a>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-xs font-medium text-ink-mute transition hover:text-ink"
          >
            关闭
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-hidden bg-paper">
          <iframe
            key={src}
            ref={frameRef}
            src={src}
            title={`${request.filename} 预览`}
            onLoad={handleLoad}
            // 不加 allow-scripts：上传的 HTML 里即使带脚本也不会执行；
            // 保留 allow-same-origin 让父页面能读取内容做引用高亮。
            sandbox="allow-same-origin"
            className="h-full w-full border-0 bg-white"
          />
        </div>

        {native && request.highlightText ? (
          <footer className="shrink-0 border-t border-ink-line bg-paper px-4 py-3">
            <p className="text-xs font-semibold text-ink-mute">
              引用片段 · {request.location}
            </p>
            <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-6 text-ink-soft">
              <mark className="rounded bg-ochre/25 px-0.5 text-ink">
                {request.highlightText}
              </mark>
            </p>
          </footer>
        ) : null}
      </aside>
    </>
  );
}
