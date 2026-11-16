import { Link } from "react-router-dom";
import type { ConversationSummary } from "../api/types";

interface Props {
  conversations: ConversationSummary[];
  onCreate: () => void;
  onDelete: (conversation: ConversationSummary) => void;
}

export function ConversationSection({ conversations, onCreate, onDelete }: Props) {
  return (
    <section className="surface p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">问答会话</h2>
          <p className="mt-1 text-sm text-ink-mute">继续讨论或开启新的问题</p>
        </div>
        <button
          type="button"
          onClick={onCreate}
          className="btn-primary min-h-9 px-3 text-xs"
        >
          新建会话 →
        </button>
      </div>

      {conversations.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-ink-line bg-paper/70 px-5 py-10 text-center">
          <div
            className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-white text-lg font-bold text-accent shadow-sm"
            aria-hidden="true"
          >
            ✦
          </div>
          <p className="mt-3 text-sm text-ink-soft">
            还没有会话。创建一个，围绕本资料集开始提问。
          </p>
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {conversations.map((conversation) => (
            <li
              key={conversation.id}
              className="group flex items-center gap-4 rounded-xl border border-ink-line px-4 py-3 transition duration-200 hover:border-accent/30 hover:bg-paper/70"
            >
              <Link to={`/conversations/${conversation.id}`} className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink transition group-hover:text-accent">
                  {conversation.title}
                </span>
                <span className="mt-1 block text-xs text-ink-mute">
                  {new Date(conversation.created_at).toLocaleString("zh-CN")}
                </span>
              </Link>
              <button
                type="button"
                onClick={() => onDelete(conversation)}
                className="row-action hover:text-vermilion"
              >
                删除
              </button>
              <Link
                to={`/conversations/${conversation.id}`}
                aria-label="打开会话"
                className="flex h-8 w-8 items-center justify-center rounded-lg bg-paper text-ink-mute transition duration-200 group-hover:translate-x-0.5 group-hover:bg-accent-wash group-hover:text-accent"
              >
                →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
