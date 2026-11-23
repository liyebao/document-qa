import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MutableRefObject,
} from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage } from "../api/client";
import { searchAll, type SearchItem } from "../api/search";
import { groupSearchItems, searchItemPath, stepIndex } from "./sidebarSearchModel";

/** 搜索请求的防抖时长：太短会打满接口，太长会让人觉得没反应。 */
const SEARCH_DEBOUNCE_MS = 250;

type SearchStatus = "idle" | "loading" | "ready" | "error";

interface SidebarSearchProps {
  /** 点击结果后通知外层关闭移动端抽屉。 */
  onNavigate?: () => void;
  /** 允许侧边栏从折叠态展开后把焦点直接交给搜索框。 */
  inputRef?: MutableRefObject<HTMLInputElement | null>;
}

export function SidebarSearch({ onNavigate, inputRef }: SidebarSearchProps) {
  const navigate = useNavigate();
  const listboxId = useId();
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [message, setMessage] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [open, setOpen] = useState(false);
  // 序号守卫：后发的响应才允许写状态，防止慢请求覆盖新结果。
  const requestSeq = useRef(0);
  const rootRef = useRef<HTMLDivElement>(null);
  // 外部 ref 与内部 ref 合并：父级（折叠态展开）需要能主动聚焦搜索框。
  const localInputRef = useRef<HTMLInputElement | null>(null);
  const setInputRef = (node: HTMLInputElement | null) => {
    localInputRef.current = node;
    if (inputRef) {
      inputRef.current = node;
    }
  };

  const trimmed = query.trim();
  const groups = useMemo(() => groupSearchItems(items), [items]);
  const flatItems = useMemo(() => groups.flatMap((group) => group.items), [groups]);

  useEffect(() => {
    if (!trimmed) {
      // 清空输入就回到空闲态，并丢弃在途请求的结果。
      requestSeq.current += 1;
      setItems([]);
      setStatus("idle");
      setMessage("");
      setActiveIndex(-1);
      return;
    }

    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setStatus("loading");
    const timer = window.setTimeout(() => {
      searchAll(trimmed)
        .then((response) => {
          if (seq !== requestSeq.current) {
            return;
          }
          setItems(response.items ?? []);
          setStatus("ready");
          setMessage("");
          setActiveIndex(-1);
        })
        .catch((error: unknown) => {
          if (seq !== requestSeq.current) {
            return;
          }
          setItems([]);
          setStatus("error");
          setMessage(errorMessage(error));
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [trimmed]);

  const commit = useCallback(
    (item: SearchItem | undefined) => {
      if (!item) {
        return;
      }
      setOpen(false);
      setQuery("");
      setItems([]);
      setStatus("idle");
      navigate(searchItemPath(item));
      onNavigate?.();
    },
    [navigate, onNavigate],
  );

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (flatItems.length === 0) {
        return;
      }
      event.preventDefault();
      setActiveIndex((current) =>
        stepIndex(current, event.key === "ArrowDown" ? 1 : -1, flatItems.length),
      );
      setOpen(true);
      return;
    }
    if (event.key === "Enter") {
      if (activeIndex >= 0 && flatItems.length > 0) {
        event.preventDefault();
        commit(flatItems[activeIndex]);
      }
      return;
    }
    if (event.key === "Escape") {
      // 先清空再收起：不清空的话用户按 Esc 只是藏起结果，输入框里还留着旧词。
      event.preventDefault();
      if (query) {
        setQuery("");
      } else {
        setOpen(false);
        event.currentTarget.blur();
      }
    }
  };

  const showPanel = open && trimmed.length > 0;
  const activeId = activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined;

  return (
    <div className="relative px-3 pb-1 pt-1" ref={rootRef}>
      <div className="relative">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="pointer-events-none absolute left-2.5 top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-ink-mute"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m16.5 16.5 4 4" />
        </svg>
        <label htmlFor={inputId} className="sr-only">
          搜索对话、文件与资料集
        </label>
        <input
          id={inputId}
          ref={setInputRef}
          type="search"
          value={query}
          autoComplete="off"
          placeholder="搜索对话 / 文件"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            // 延迟收起，给「点击结果」留出时间，否则 blur 先触发会把面板拆掉。
            window.setTimeout(() => setOpen(false), 120);
          }}
          onKeyDown={handleKeyDown}
          className="field w-full py-1.5 pl-8 pr-2 text-[13px]"
        />
      </div>

      {showPanel ? (
        <div className="absolute left-2 right-2 top-full z-30 mt-1 overflow-hidden rounded-xl border border-ink-line bg-paper shadow-card">
          <div
            id={listboxId}
            role="listbox"
            aria-label="搜索结果"
            className="max-h-[340px] overflow-y-auto p-1"
          >
            {status === "loading" && flatItems.length === 0 ? (
              <p role="status" className="px-2 py-3 text-xs text-ink-mute">
                正在搜索…
              </p>
            ) : null}

            {status === "error" ? (
              <div role="alert" className="px-2 py-2 text-xs text-vermilion">
                <p>{message || "搜索失败，请重试"}</p>
              </div>
            ) : null}

            {status === "ready" && flatItems.length === 0 ? (
              <p role="status" className="px-2 py-3 text-xs text-ink-mute">
                没有找到与「{trimmed}」相关的内容
              </p>
            ) : null}

            {groups.map((group) => (
              <div key={group.kind} className="pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold tracking-wide text-ink-mute">
                  {group.label}
                  <span className="ml-1 font-normal text-ink-soft">
                    {group.items.length}
                  </span>
                </p>
                {group.items.map((item) => {
                  const index = flatItems.indexOf(item);
                  const active = index === activeIndex;
                  return (
                    <button
                      key={`${item.kind}-${item.id}`}
                      type="button"
                      id={`${listboxId}-option-${index}`}
                      role="option"
                      aria-selected={active}
                      // 阻止 mousedown 抢焦点，否则输入框先 blur，面板来不及响应点击。
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => commit(item)}
                      className={`flex w-full flex-col items-start rounded-lg px-2 py-1.5 text-left transition ${
                        active
                          ? "bg-accent-wash text-accent"
                          : "text-ink hover:bg-paper-deep"
                      }`}
                    >
                      <span className="w-full truncate text-[13px] font-medium">
                        {item.label}
                      </span>
                      {item.sublabel ? (
                        <span className="w-full truncate text-[11px] text-ink-mute">
                          {item.sublabel}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
