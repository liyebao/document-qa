import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link, useParams } from "react-router-dom";
import { errorMessage } from "../api/client";
import { getConversation, sendMessageStream } from "../api/conversations";
import { listDocuments } from "../api/documents";
import type { ConversationDetail, DocumentItem, Message } from "../api/types";
import { ChatMessage } from "../components/ChatMessage";

export function ConversationPage() {
  const params = useParams<{ conversationId: string }>();
  const conversationId = params.conversationId ?? "";

  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [scopeIds, setScopeIds] = useState<string[]>([]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 只有用户停留在底部时才自动跟随；上翻查看历史时不抢滚动位置。
  const stickToBottom = useRef(true);
  // 流式增量先攒在 ref 里，按帧合并成一次 state 更新，避免每个 token 都全量重渲染。
  const streamBuffer = useRef("");
  const streamFrame = useRef<number | null>(null);

  const load = useCallback(async () => {
    if (!conversationId) {
      return;
    }
    setLoading(true);
    try {
      const detail = await getConversation(conversationId);
      setConversation(detail);
      const items = await listDocuments(detail.collection_id);
      const usable = items.filter(
        (item) => item.status === "ready" && item.is_current && item.is_enabled,
      );
      setDocuments(usable);
      setScopeIds((current) =>
        current.filter((id) => usable.some((item) => item.id === id)),
      );
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    void load();
  }, [load]);

  const flushStream = useCallback(() => {
    streamFrame.current = null;
    setStreamText(streamBuffer.current);
  }, []);

  const appendDelta = useCallback(
    (text: string) => {
      streamBuffer.current += text;
      if (streamFrame.current === null) {
        streamFrame.current = window.requestAnimationFrame(flushStream);
      }
    },
    [flushStream],
  );

  const resetStream = useCallback(() => {
    if (streamFrame.current !== null) {
      window.cancelAnimationFrame(streamFrame.current);
      streamFrame.current = null;
    }
    streamBuffer.current = "";
    setStreamText("");
  }, []);

  useEffect(() => {
    return () => {
      if (streamFrame.current !== null) {
        window.cancelAnimationFrame(streamFrame.current);
      }
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !stickToBottom.current) {
      return;
    }
    // 直接赋值而不是 smooth：平滑滚动会和渲染抢主线程，长回答时明显卡顿。
    container.scrollTop = container.scrollHeight;
  }, [conversation?.messages.length, sending, streamText]);

  function handleScroll() {
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    stickToBottom.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < 120;
  }

  async function submitQuestion() {
    const content = question.trim();
    if (!content || sending || !conversation) {
      return;
    }
    setSending(true);
    setError(null);
    setQuestion("");
    resetStream();
    // 用户主动提问时重新跟随底部，忽略此前上翻留下的状态。
    stickToBottom.current = true;

    const pendingId = `pending-${Date.now()}`;
    const pendingMessage: Message = {
      id: pendingId,
      role: "user",
      content,
      status: "completed",
      created_at: new Date().toISOString(),
      citations: [],
    };
    setConversation((current) =>
      current ? { ...current, messages: [...current.messages, pendingMessage] } : current,
    );

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await sendMessageStream(
        conversationId,
        content,
        scopeIds,
        {
          onDelta: appendDelta,
          onDone: ({ user_message, assistant_message }) => {
            setConversation((current) =>
              current
                ? {
                    ...current,
                    messages: [
                      ...current.messages.map((message) =>
                        message.id === pendingId ? user_message : message,
                      ),
                      assistant_message,
                    ],
                  }
                : current,
            );
            resetStream();
          },
          onError: (message) => {
            setError(message);
            resetStream();
            void getConversation(conversationId)
              .then(setConversation)
              .catch(() => undefined);
          },
        },
        { signal: controller.signal },
      );
    } catch (err) {
      setConversation((current) =>
        current
          ? {
              ...current,
              messages: current.messages.filter((message) => message.id !== pendingId),
            }
          : current,
      );
      if (err instanceof DOMException && err.name === "AbortError") {
        // 用户主动停止：后端会保存已生成的部分，重新拉取即可看到。
        setError("已停止生成");
        void getConversation(conversationId)
          .then(setConversation)
          .catch(() => undefined);
      } else {
        setError(errorMessage(err));
        setQuestion(content);
      }
    } finally {
      abortRef.current = null;
      setSending(false);
      resetStream();
    }
  }

  function stopStream() {
    abortRef.current?.abort();
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitQuestion();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  if (loading) {
    return <p className="py-10 text-xs text-ink-mute">读取会话…</p>;
  }

  if (!conversation) {
    return (
      <div className="space-y-4">
        <p className="border-l-2 border-vermilion bg-vermilion-wash px-3 py-2 text-xs text-vermilion">
          {error ?? "会话不存在"}
        </p>
        <Link to="/" className="link-quiet text-[13px]">
          ← 返回资料集列表
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col">
      {/* 紧凑标题栏：与主流对话应用一致，只保留返回、标题和范围入口。 */}
      <div className="mx-auto flex w-full max-w-3xl shrink-0 items-start gap-3 border-b border-ink-line pb-3">
        <div className="min-w-0 flex-1">
          <Link
            to={`/collections/${conversation.collection_id}`}
            className="text-xs font-medium text-ink-mute transition hover:text-accent"
          >
            ← 返回资料集
          </Link>
          <h1 className="mt-1 truncate text-lg font-semibold tracking-tight text-ink sm:text-xl">
            {conversation.title}
          </h1>
        </div>

        <div className="relative shrink-0">
          <button
            type="button"
            onClick={() => setScopeOpen((open) => !open)}
            aria-expanded={scopeOpen}
            className="rounded-full border border-ink-line bg-white px-3 py-1.5 text-xs font-medium text-ink-soft transition hover:border-accent/40 hover:text-accent"
          >
            {scopeIds.length === 0 ? "整个资料集" : `已选 ${scopeIds.length} 份`}
            <span className="ml-1">{scopeOpen ? "▴" : "▾"}</span>
          </button>

          {scopeOpen && (
            <div className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-ink-line bg-white p-2 shadow-lift">
              <div className="flex items-center justify-between px-2 py-1">
                <span className="text-xs font-semibold text-ink-soft">检索范围</span>
                {scopeIds.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setScopeIds([])}
                    className="text-xs font-medium text-accent transition hover:text-accent-dark"
                  >
                    恢复整个资料集
                  </button>
                )}
              </div>
              <div className="mt-1 max-h-56 overflow-y-auto">
                {documents.length === 0 ? (
                  <p className="px-2 py-3 text-sm text-ink-mute">
                    当前资料集还没有可检索的文件。
                  </p>
                ) : (
                  documents.map((document) => (
                    <label
                      key={document.id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 text-sm text-ink-soft transition hover:bg-paper hover:text-ink"
                    >
                      <input
                        type="checkbox"
                        checked={scopeIds.includes(document.id)}
                        onChange={(event) =>
                          setScopeIds((current) =>
                            event.target.checked
                              ? [...current, document.id]
                              : current.filter((id) => id !== document.id),
                          )
                        }
                      />
                      <span className="truncate">{document.filename}</span>
                      <span className="ml-auto shrink-0 text-xs text-ink-mute">
                        {document.format}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="mx-auto min-h-0 w-full max-w-3xl flex-1 space-y-8 overflow-y-auto py-4 pr-1"
      >
        {error && (
          <p
            role="alert"
            className="rounded-xl border border-vermilion/20 bg-vermilion-wash px-4 py-3 text-sm leading-relaxed text-vermilion"
          >
            {error}
          </p>
        )}

        {conversation.messages.length === 0 ? (
          <div className="flex min-h-[50vh] flex-col items-center justify-center text-center">
            <span
              aria-hidden="true"
              className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-wash text-2xl font-bold text-accent"
            >
              问
            </span>
            <p className="mt-5 text-lg font-semibold text-ink">从资料中开始提问</p>
            <p className="mt-2 max-w-[42ch] text-sm leading-6 text-ink-mute">
              试着询问某份文档里的结论、数据或定义，回答会标注对应的来源片段。
            </p>
          </div>
        ) : (
          conversation.messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))
        )}

        {streamText && (
          <ChatMessage
            streaming
            message={{
              id: "streaming",
              role: "assistant",
              content: streamText,
              status: "completed",
              created_at: new Date().toISOString(),
              citations: [],
            }}
          />
        )}

        {sending && !streamText && (
          <div className="flex items-center gap-3 text-sm text-ink-mute">
            <span className="flex gap-1" aria-hidden="true">
              {[0, 1, 2].map((index) => (
                <span
                  key={index}
                  className="h-1.5 w-1.5 animate-blink rounded-full bg-accent"
                  style={{ animationDelay: `${index * 160}ms` }}
                />
              ))}
            </span>
            正在检索资料并生成回答…
          </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="mx-auto w-full max-w-3xl shrink-0 border-t border-ink-line pt-3"
      >
        <div className="flex items-end gap-2 rounded-2xl border border-ink-line bg-white p-2 shadow-lift focus-within:border-accent/40">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            maxLength={4000}
            aria-label="提问内容"
            placeholder="围绕当前资料集提问…"
            className="min-h-[56px] flex-1 resize-none bg-transparent px-3 py-2 text-sm leading-6 text-ink outline-none placeholder:text-ink-mute"
          />
          {sending ? (
            <button
              type="button"
              onClick={stopStream}
              className="min-h-10 shrink-0 rounded-full border border-ink-line px-5 text-sm font-medium text-ink-soft transition hover:border-vermilion/40 hover:text-vermilion"
            >
              停止生成
            </button>
          ) : (
            <button
              type="submit"
              disabled={!question.trim()}
              className="btn-primary min-h-10 shrink-0 px-5"
            >
              发送
            </button>
          )}
        </div>
        <p className="mt-2 flex items-center justify-between gap-3 px-1 text-xs text-ink-mute">
          <span className="truncate">Enter 发送 · Shift + Enter 换行</span>
          <span className="hidden shrink-0 sm:inline">回答仅依据本资料集的检索片段</span>
          <span className="shrink-0 font-mono">{question.length} / 4000</span>
        </p>
      </form>
    </div>
  );
}
