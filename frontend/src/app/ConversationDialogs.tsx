import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { errorMessage } from "../api/client";
import { deleteConversation, renameConversation } from "../api/conversations";
import { useFocusTrap } from "./useFocusTrap";

export interface ConversationTarget {
  id: string;
  title: string;
}

/**
 * 侧边栏行内菜单用的两个小弹窗。
 * 统一 portal 到 body：移动端抽屉带 `animate-slide-in`（transform），
 * 会给内部 fixed 元素建立新的包含块，不用 portal 弹窗会被裁在抽屉里。
 */

function Overlay({ children }: { children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-4 sm:items-center">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
        aria-hidden="true"
      />
      <div className="relative w-full max-w-sm">{children}</div>
    </div>
  );
}

interface RenameDialogProps {
  target: ConversationTarget | null;
  onClose: () => void;
  onSaved: (title: string) => void;
}

export function RenameDialog({ target, onClose, onSaved }: RenameDialogProps) {
  const [title, setTitle] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const open = target !== null;

  useFocusTrap(panelRef, open);

  useEffect(() => {
    if (!target) {
      return;
    }
    setTitle(target.title);
    setError(null);
    setPending(false);
    // 打开时直接选中原标题，改名通常就是整句替换。
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [target]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!target) {
    return null;
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const next = title.trim();
    if (!next || pending) {
      return;
    }
    setPending(true);
    setError(null);
    renameConversation(target.id, next)
      .then(() => {
        onSaved(next);
      })
      .catch((err: unknown) => {
        setError(errorMessage(err));
      })
      .finally(() => {
        setPending(false);
      });
  };

  return createPortal(
    <Overlay>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="重命名对话"
        className="surface relative w-full rounded-2xl p-5 animate-rise"
      >
        <h2 className="font-serif text-lg text-ink">重命名对话</h2>
        <p className="mt-1 text-xs text-ink-soft">只改标题，不影响已保存的消息。</p>
        <form onSubmit={handleSubmit} className="mt-4">
          <label htmlFor="rename-conversation-input" className="sr-only">
            对话标题
          </label>
          <input
            id="rename-conversation-input"
            ref={inputRef}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={120}
            className="field w-full"
            placeholder="给这段对话起个名字"
          />
          {error ? (
            <p role="alert" className="mt-2 text-xs text-vermilion">
              {error}
            </p>
          ) : null}
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              取消
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={pending || title.trim().length === 0}
            >
              {pending ? "保存中…" : "保存"}
            </button>
          </div>
        </form>
      </div>
    </Overlay>,
    document.body,
  );
}

interface DeleteConversationDialogProps {
  target: ConversationTarget | null;
  onClose: () => void;
  onDeleted: () => void;
}

export function DeleteConversationDialog({
  target,
  onClose,
  onDeleted,
}: DeleteConversationDialogProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const open = target !== null;

  // 焦点默认落在「取消」上：删除是不可逆操作，别让回车顺手删掉。
  useFocusTrap(panelRef, open, cancelRef);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setPending(false);
    cancelRef.current?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!target) {
    return null;
  }

  const handleConfirm = () => {
    if (pending) {
      return;
    }
    setPending(true);
    setError(null);
    deleteConversation(target.id)
      .then(() => {
        onDeleted();
      })
      .catch((err: unknown) => {
        setError(errorMessage(err));
      })
      .finally(() => {
        setPending(false);
      });
  };

  return createPortal(
    <Overlay>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="删除对话"
        className="surface relative w-full rounded-2xl p-5 animate-rise"
      >
        <h2 className="font-serif text-lg text-ink">删除这段对话？</h2>
        <p className="mt-2 text-sm text-ink-soft">
          「{target.title}」及其消息会被永久删除，无法恢复。
        </p>
        {error ? (
          <p role="alert" className="mt-2 text-xs text-vermilion">
            {error}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            ref={cancelRef}
            className="btn btn-ghost"
            onClick={onClose}
            disabled={pending}
          >
            取消
          </button>
          <button
            type="button"
            className="btn bg-vermilion text-paper hover:bg-vermilion-dark"
            onClick={handleConfirm}
            disabled={pending}
          >
            {pending ? "删除中…" : "删除"}
          </button>
        </div>
      </div>
    </Overlay>,
    document.body,
  );
}

interface DeleteManyDialogProps {
  /** null 表示关闭；否则为本次要删除的会话（多选结果）。 */
  targets: ConversationTarget[] | null;
  onClose: () => void;
  /** 已成功删除的 id：交给侧边栏刷新列表、收缩勾选。 */
  onDeleted: (ids: string[]) => void;
}

/**
 * 批量删除确认。后端只有单条删除接口，这里并行删除并汇总结果：
 * 部分失败时把失败项留在对话框里，可以重试或直接关掉。
 */
export function DeleteManyConversationsDialog({
  targets,
  onClose,
  onDeleted,
}: DeleteManyDialogProps) {
  const [queue, setQueue] = useState<ConversationTarget[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const open = targets !== null && targets.length > 0;

  useFocusTrap(panelRef, open, cancelRef);

  useEffect(() => {
    if (!open) {
      return;
    }
    // 每次打开都以最新的勾选结果为准。
    setQueue(targets ?? []);
    setError(null);
    setPending(false);
    cancelRef.current?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, targets, onClose]);

  if (!open) {
    return null;
  }

  const handleConfirm = () => {
    if (pending || queue.length === 0) {
      return;
    }
    setPending(true);
    setError(null);
    const batch = queue;
    Promise.allSettled(batch.map((target) => deleteConversation(target.id)))
      .then((results) => {
        const deleted: string[] = [];
        let firstError: unknown = null;
        results.forEach((result, index) => {
          if (result.status === "fulfilled") {
            deleted.push(batch[index].id);
          } else if (firstError === null) {
            firstError = result.reason;
          }
        });
        const rest = batch.filter((target) => !deleted.includes(target.id));
        setQueue(rest);
        if (deleted.length > 0) {
          onDeleted(deleted);
        }
        if (firstError !== null) {
          setError(
            `有 ${rest.length} 段对话未删除：${errorMessage(firstError)}，可重试或稍后再试。`,
          );
        }
        if (rest.length === 0) {
          onClose();
        }
      })
      .finally(() => {
        setPending(false);
      });
  };

  return createPortal(
    <Overlay>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="批量删除对话"
        className="surface relative w-full rounded-2xl p-5 animate-rise"
      >
        <h2 className="font-serif text-lg text-ink">
          删除选中的 {queue.length} 段对话？
        </h2>
        <p className="mt-2 text-sm text-ink-soft">
          这些对话及其消息会被永久删除，无法恢复。
        </p>
        <ul className="mt-3 max-h-32 space-y-1 overflow-y-auto rounded-xl bg-paper-deep px-3 py-2 text-xs leading-5 text-ink-soft">
          {queue.slice(0, 4).map((target) => (
            <li key={target.id} className="truncate">
              · {target.title}
            </li>
          ))}
          {queue.length > 4 ? <li>…等共 {queue.length} 段</li> : null}
        </ul>
        {error ? (
          <p role="alert" className="mt-2 text-xs leading-5 text-vermilion">
            {error}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            ref={cancelRef}
            className="btn btn-ghost"
            onClick={onClose}
            disabled={pending}
          >
            取消
          </button>
          <button
            type="button"
            className="btn bg-vermilion text-paper hover:bg-vermilion-dark"
            onClick={handleConfirm}
            disabled={pending}
          >
            {pending ? "删除中…" : "删除"}
          </button>
        </div>
      </div>
    </Overlay>,
    document.body,
  );
}
