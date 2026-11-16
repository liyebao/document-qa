import { memo, useCallback, useEffect, useRef, useState } from "react";
import type { Message } from "../api/types";
import { copyText } from "../lib/clipboard";
import { CitationCard } from "./CitationCard";
import { MarkdownAnswer } from "./MarkdownAnswer";

function formatMessageTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const time = date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return date.toDateString() === new Date().toDateString()
    ? time
    : `${date.getMonth() + 1}月${date.getDate()}日 ${time}`;
}

function ChatMessageBase({
  message,
  streaming = false,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const [copyState, setCopyState] = useState<"idle" | "done" | "error">("idle");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const ok = await copyText(message.content);
    setCopyState(ok ? "done" : "error");
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => setCopyState("idle"), 2000);
  }, [message.content]);

  // 时间与复制放在文字右下方，平时隐藏，靠近消息或键盘聚焦时才出现。
  const actions = (
    <div className="flex items-center justify-end gap-2 text-xs text-ink-mute opacity-0 transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100 max-sm:opacity-100">
      <time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time>
      <button
        type="button"
        onClick={() => void handleCopy()}
        aria-live="polite"
        className={`rounded-md px-1.5 py-0.5 transition hover:bg-paper-deep ${
          copyState === "done"
            ? "text-jade"
            : copyState === "error"
              ? "text-vermilion"
              : "hover:text-ink"
        }`}
      >
        {copyState === "done"
          ? "已复制"
          : copyState === "error"
            ? "复制失败"
            : "全部复制"}
      </button>
    </div>
  );

  if (isUser) {
    return (
      <div className="group flex animate-rise flex-col items-end gap-1.5">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-3 text-sm leading-7 text-white shadow-sm selection:bg-white selection:text-accent sm:max-w-[75%]">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
        {!streaming && actions}
      </div>
    );
  }

  return (
    <div className="group animate-rise">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent-wash text-sm font-bold leading-none text-accent"
        >
          答
        </span>
        <span className="text-sm font-semibold text-ink">知识助手</span>
      </div>

      <div className="ml-10 mt-2">
        {streaming ? (
          // 流式阶段只渲染纯文本：既避免半截 Markdown 标记裸露，也避免每个 delta 全量重解析。
          <p className="whitespace-pre-wrap break-words text-sm leading-7 text-ink sm:text-[15px]">
            {message.content}
          </p>
        ) : (
          <div className="break-words text-sm leading-7 text-ink sm:text-[15px]">
            <MarkdownAnswer content={message.content} citations={message.citations} />
          </div>
        )}

        {message.status === "insufficient" && (
          <p className="mt-3 rounded-xl border border-ochre/30 bg-ochre-wash px-4 py-3 text-sm leading-relaxed text-ochre">
            本次回答未找到足够的资料依据。
          </p>
        )}

        {message.status === "failed" && (
          <p className="mt-3 rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm leading-relaxed text-vermilion">
            本次回答生成失败，可以稍后重新提问。
          </p>
        )}

        {message.citations.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-semibold text-ink-mute">引用来源</p>
            <div className="mt-2 space-y-2">
              {message.citations.map((citation) => (
                <CitationCard
                  key={citation.id}
                  citation={citation}
                  index={citation.marker_index}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {!streaming && <div className="ml-10 mt-1.5">{actions}</div>}
    </div>
  );
}

// 历史消息的 message 引用稳定，memo 可避免每个流式 delta 触发整段历史重渲染。
export const ChatMessage = memo(ChatMessageBase);
