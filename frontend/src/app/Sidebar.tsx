import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { SidebarSearch } from "../components/SidebarSearch";
import { ConversationRowMenu } from "./ConversationRowMenu";
import {
  DeleteConversationDialog,
  RenameDialog,
  type ConversationTarget,
} from "./ConversationDialogs";
import {
  RECENT_GROUP_LIMIT,
  formatActivityLabel,
  groupConversationsByCollection,
  isGroupCollapsed,
  notifyConversationRenamed,
  notifyConversationsChanged,
  parseCollapsedGroups,
  serializeCollapsedGroups,
  takeWithLimit,
  toggleCollapsedGroup,
  type CollapsedGroupMap,
  type RecentCollectionGroup,
  type RecentConversationsState,
} from "./recent";

const COLLAPSED_GROUPS_STORAGE_KEY = "kb:sidebar-collapsed-groups";

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span
        className={`flex items-center justify-center rounded-xl bg-accent font-sans font-bold leading-none text-white shadow-sm ${
          compact ? "h-8 w-8 text-base" : "h-9 w-9 text-lg"
        }`}
      >
        知
      </span>
      <span className="flex min-w-0 flex-col">
        <span
          className={`truncate font-sans font-bold leading-tight text-ink ${
            compact ? "text-sm" : "text-[15px]"
          }`}
        >
          个人知识库
        </span>
        <span className="mt-0.5 truncate text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-mute">
          Knowledge Archive
        </span>
      </span>
    </span>
  );
}

function iconClass() {
  return "h-[18px] w-[18px]";
}

function LibraryIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={iconClass()}
    >
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10v16H5.5A1.5 1.5 0 0 1 4 18.5z" />
      <path d="M10 4h4.5A1.5 1.5 0 0 1 16 5.5v13a1.5 1.5 0 0 1-1.5 1.5H10z" />
      <path d="m17.4 6.2 2.2 12.4" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={iconClass()}
    >
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.6 1.6 0 0 0 .32 1.77l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.6 1.6 0 0 0-1.77-.32 1.6 1.6 0 0 0-.97 1.46V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1.05-1.46 1.6 1.6 0 0 0-1.77.32l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.6 1.6 0 0 0 4.6 15a1.6 1.6 0 0 0-1.46-.97H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.46-1.05 1.6 1.6 0 0 0-.32-1.77l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.6 1.6 0 0 0 8.84 4.7h.08A1.6 1.6 0 0 0 9.9 3.24V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 .97 1.46 1.6 1.6 0 0 0 1.77-.32l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.6 1.6 0 0 0-.32 1.77v.08c.24.58.8.97 1.43.97H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5.97z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={iconClass()}
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m16.5 16.5 4 4" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

/** 折叠/展开侧边栏的箭头：折叠态朝右（点开），展开态朝左（收起）。 */
function CollapseIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
      {collapsed ? <path d="m13 10 2 2-2 2" /> : <path d="m15 10-2 2 2 2" />}
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="h-4 w-4">
      <circle cx="5" cy="12" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="19" cy="12" r="1.6" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`h-3.5 w-3.5 shrink-0 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

const NAV_BASE =
  "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition duration-200 ease-out";

/** 折叠态图标按钮的统一外观，与展开态 NAV_BASE 的高度（36px）保持一致。 */
const RAIL_BUTTON =
  "relative flex h-9 w-9 items-center justify-center rounded-lg text-ink-soft transition duration-200 ease-out hover:bg-paper hover:text-ink";

function readCollapsedGroups(): CollapsedGroupMap {
  try {
    return parseCollapsedGroups(
      window.localStorage.getItem(COLLAPSED_GROUPS_STORAGE_KEY),
    );
  } catch {
    // 隐私模式等场景下 localStorage 可能不可用，退化成全部展开。
    return {};
  }
}

interface Props {
  pathname: string;
  recent: RecentConversationsState;
  /** 桌面端折叠态（72px 图标栏）；移动端抽屉始终展开，不受影响。 */
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNewConversation: () => void;
  onNavigate?: () => void;
  onClose?: () => void;
}

export function Sidebar({
  pathname,
  recent,
  collapsed = false,
  onToggleCollapsed,
  onNewConversation,
  onNavigate,
  onClose,
}: Props) {
  const libraryActive = pathname === "/" || pathname.startsWith("/collections");
  const settingsActive = pathname.startsWith("/settings");
  const conversationCount = recent.items.length;
  const idPrefix = useId();

  // 折叠状态持久化：只记「哪些组被收起」，默认全展开，避免记忆把新组也藏起来。
  const [collapsedGroups, setCollapsedGroups] =
    useState<CollapsedGroupMap>(readCollapsedGroups);
  // “显示更多”只影响本次浏览，不落盘；刷新后回到每组 6 条的紧凑状态。
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const [menuTarget, setMenuTarget] = useState<{
    target: ConversationTarget;
    anchor: HTMLElement;
  } | null>(null);
  const [renameTarget, setRenameTarget] = useState<ConversationTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ConversationTarget | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        COLLAPSED_GROUPS_STORAGE_KEY,
        serializeCollapsedGroups(collapsedGroups),
      );
    } catch {
      // 存不下就算了，折叠状态只影响观感
    }
  }, [collapsedGroups]);

  const collectionGroups = groupConversationsByCollection(recent.items);
  const navItems = [
    { to: "/", label: "资料库", active: libraryActive, Icon: LibraryIcon },
    { to: "/settings/models", label: "设置", active: settingsActive, Icon: SettingsIcon },
  ];

  const handleRenameSaved = (title: string) => {
    const id = renameTarget?.id;
    setRenameTarget(null);
    if (id) {
      // 列表和对话页标题都要跟着变：一个走列表事件，一个走标题事件。
      notifyConversationRenamed(id, title);
    }
    notifyConversationsChanged();
    void recent.refresh();
  };

  const handleDeleted = () => {
    setDeleteTarget(null);
    notifyConversationsChanged();
    void recent.refresh();
  };

  if (collapsed) {
    return (
      <aside className="flex h-full min-h-0 w-full flex-col items-center border-r border-ink-line bg-white py-4">
        <Link
          to="/"
          onClick={onNavigate}
          aria-label="个人知识库首页"
          data-tip="个人知识库"
          className="rail-tip flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-lg font-bold leading-none text-white shadow-sm"
        >
          知
        </Link>

        {onToggleCollapsed ? (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label="展开侧边栏"
            aria-expanded={false}
            data-tip="展开侧边栏"
            className={`${RAIL_BUTTON} mt-2`}
          >
            <CollapseIcon collapsed />
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => {
            // 折叠态下没有输入框，先展开再把焦点交给搜索框（等一帧让展开后的节点渲染出来）。
            onToggleCollapsed?.();
            window.setTimeout(() => searchInputRef.current?.focus(), 0);
          }}
          aria-label="搜索对话、文件与资料集"
          data-tip="搜索"
          className={`${RAIL_BUTTON} mt-3`}
        >
          <SearchIcon />
        </button>

        <button
          type="button"
          onClick={onNewConversation}
          aria-label="新建对话"
          data-tip="新建对话"
          className="mt-2 flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-sm transition duration-200 ease-out hover:bg-accent-dark"
        >
          <PlusIcon />
        </button>

        <nav aria-label="主导航" className="mt-3 flex flex-col items-center gap-1">
          {navItems.map(({ to, label, active, Icon }) => (
            <Link
              key={to}
              to={to}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              aria-label={label}
              data-tip={label}
              className={`rail-tip ${RAIL_BUTTON} ${active ? "bg-accent-wash text-accent" : ""}`}
            >
              <Icon />
            </Link>
          ))}
        </nav>

        <div className="mt-auto flex flex-col items-center">
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭导航"
              data-tip="关闭导航"
              className={`${RAIL_BUTTON} rail-tip`}
            >
              <CloseIcon />
            </button>
          ) : null}
          <span
            aria-hidden="true"
            data-tip="本地单用户模式"
            className="rail-tip mt-2 h-1.5 w-1.5 rounded-full bg-jade"
          />
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-full min-h-0 w-full flex-col border-r border-ink-line bg-white">
      <div className="flex shrink-0 items-center justify-between gap-2 px-4 pb-3 pt-5">
        <Link to="/" onClick={onNavigate} aria-label="个人知识库首页" className="min-w-0">
          <BrandMark />
        </Link>
        <div className="flex shrink-0 items-center gap-1">
          {onToggleCollapsed ? (
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-label="折叠侧边栏"
              aria-expanded
              data-tip="折叠侧边栏"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-mute transition hover:bg-paper hover:text-ink"
            >
              <CollapseIcon collapsed={false} />
            </button>
          ) : null}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭导航"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-ink-mute transition hover:bg-paper hover:text-ink"
            >
              <CloseIcon />
            </button>
          )}
        </div>
      </div>

      <SidebarSearch inputRef={searchInputRef} onNavigate={onNavigate} />

      <div className="shrink-0 px-3 pt-2">
        <button
          type="button"
          onClick={onNewConversation}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition duration-200 ease-out hover:bg-accent-dark"
        >
          <PlusIcon />
          新建对话
        </button>
      </div>

      <nav aria-label="主导航" className="mt-3 flex shrink-0 flex-col gap-0.5 px-2">
        {navItems.map(({ to, label, active, Icon }) => (
          <Link
            key={to}
            to={to}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`${NAV_BASE} ${
              active
                ? "bg-accent-wash text-accent"
                : "text-ink-soft hover:bg-paper hover:text-ink"
            }`}
          >
            <Icon />
            {label}
          </Link>
        ))}
      </nav>

      <div className="mt-5 flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center justify-between px-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-mute">
            最近
          </h2>
          {conversationCount > 0 && (
            <span className="text-[11px] tabular-nums text-ink-mute">
              {conversationCount}
            </span>
          )}
        </div>
        {/* 两种分组口径同时存在，这里说明主次，免得用户以为时间分组被砍掉了。 */}
        <p className="shrink-0 px-4 pb-2 pt-1 text-[10px] leading-4 text-ink-mute">
          按资料集分组，组内按最近活动倒序；每行的「今天 / 昨天 / N
          天前」沿用原来的时间口径。
        </p>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4" id="recent-list">
          {recent.loading ? (
            <div className="space-y-2 px-2 py-1" aria-label="正在读取最近会话">
              {[0, 1, 2].map((index) => (
                <div key={index} className="h-9 animate-pulse rounded-lg bg-paper-deep" />
              ))}
            </div>
          ) : recent.error ? (
            <div className="mx-2 rounded-xl bg-vermilion-wash px-3 py-3">
              <p className="text-[11px] leading-5 text-vermilion">{recent.error}</p>
              <button
                type="button"
                onClick={() => void recent.refresh()}
                className="mt-1 text-[11px] font-semibold text-vermilion underline-offset-2 hover:underline"
              >
                重新加载
              </button>
            </div>
          ) : collectionGroups.length === 0 ? (
            <p className="px-3 py-2 text-[11px] leading-5 text-ink-mute">
              还没有会话。进入资料集新建对话后，会出现在这里。
            </p>
          ) : (
            collectionGroups.map((group) => (
              <RecentCollectionSection
                key={group.key}
                group={group}
                pathname={pathname}
                idPrefix={idPrefix}
                now={new Date()}
                collapsed={isGroupCollapsed(collapsedGroups, group.key)}
                expanded={expandedGroups[group.key] === true}
                onToggleCollapsed={() =>
                  setCollapsedGroups((current) =>
                    toggleCollapsedGroup(current, group.key),
                  )
                }
                onToggleExpanded={() =>
                  setExpandedGroups((current) => ({
                    ...current,
                    [group.key]: !current[group.key],
                  }))
                }
                onNavigate={onNavigate}
                onOpenMenu={(target, anchor) => setMenuTarget({ target, anchor })}
                menuOpenId={menuTarget?.target.id ?? null}
              />
            ))
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-ink-line px-4 py-3">
        <p className="flex items-center gap-2 text-[11px] leading-5 text-ink-mute">
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-jade" />
          本地单用户模式 · 资料仅存本机
        </p>
      </div>

      {menuTarget ? (
        <ConversationRowMenu
          anchor={menuTarget.anchor}
          title={menuTarget.target.title}
          onClose={() => setMenuTarget(null)}
          onRename={() => {
            setRenameTarget(menuTarget.target);
            setMenuTarget(null);
          }}
          onDelete={() => {
            setDeleteTarget(menuTarget.target);
            setMenuTarget(null);
          }}
        />
      ) : null}

      <RenameDialog
        target={renameTarget}
        onClose={() => setRenameTarget(null)}
        onSaved={handleRenameSaved}
      />
      <DeleteConversationDialog
        target={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onDeleted={handleDeleted}
      />
    </aside>
  );
}

interface RecentSectionProps {
  group: RecentCollectionGroup;
  pathname: string;
  idPrefix: string;
  now: Date;
  collapsed: boolean;
  expanded: boolean;
  onToggleCollapsed: () => void;
  onToggleExpanded: () => void;
  onNavigate?: () => void;
  onOpenMenu: (target: ConversationTarget, anchor: HTMLElement) => void;
  menuOpenId: string | null;
}

/**
 * 一个资料集分组。用 `content-visibility: auto` 让屏幕外的组跳过渲染与布局，
 * 由于组内最多先渲染 RECENT_GROUP_LIMIT 条，长列表的 DOM 规模也保持可控。
 */
function RecentCollectionSection({
  group,
  pathname,
  idPrefix,
  now,
  collapsed,
  expanded,
  onToggleCollapsed,
  onToggleExpanded,
  onNavigate,
  onOpenMenu,
  menuOpenId,
}: RecentSectionProps) {
  const safeKey = group.key.replace(/[^a-zA-Z0-9_-]/g, "-");
  const headerId = `${idPrefix}-group-${safeKey}`;
  const listId = `${idPrefix}-items-${safeKey}`;
  const { visible, hiddenCount } = takeWithLimit(group.items, RECENT_GROUP_LIMIT);
  const shown = expanded ? group.items : visible;

  return (
    <section className="cv-group mb-2 last:mb-0" aria-labelledby={headerId}>
      <h3>
        <button
          type="button"
          id={headerId}
          onClick={onToggleCollapsed}
          aria-expanded={!collapsed}
          aria-controls={listId}
          className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition hover:bg-paper"
        >
          <ChevronIcon open={!collapsed} />
          <span className="min-w-0 flex-1 truncate text-[11px] font-semibold tracking-[0.02em] text-ink-soft">
            {group.label}
          </span>
          <span className="shrink-0 text-[10px] tabular-nums text-ink-mute">
            {group.count}
          </span>
        </button>
      </h3>

      {/* 折叠时直接不渲染列表：既让 aria-controls 仍指向一个真实存在的容器，
          又真正把行从 DOM 里拿掉（hidden 只是视觉隐藏，节点数照样堆着） */}
      <div id={listId}>
        {collapsed ? null : (
          <ul className="space-y-0.5">
            {shown.map((item) => {
              const active = pathname === `/conversations/${item.id}`;
              const menuOpen = menuOpenId === item.id;
              return (
                <li key={item.id} className="group relative">
                  <Link
                    to={`/conversations/${item.id}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={`${item.title} · ${formatActivityLabel(item, now)}`}
                    className={`flex items-center gap-2.5 rounded-lg py-2 pl-2 pr-8 transition duration-200 ease-out ${
                      active ? "bg-accent-wash" : "hover:bg-paper"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold ${
                        active
                          ? "bg-white text-accent shadow-sm"
                          : "bg-paper text-ink-mute group-hover:text-accent"
                      }`}
                    >
                      问
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={`block truncate text-[13px] font-medium ${
                          active ? "text-accent" : "text-ink-soft group-hover:text-ink"
                        }`}
                      >
                        {item.title}
                      </span>
                      <span className="mt-0.5 block truncate text-[11px] text-ink-mute">
                        {formatActivityLabel(item, now)}
                      </span>
                    </span>
                  </Link>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      onOpenMenu({ id: item.id, title: item.title }, event.currentTarget);
                    }}
                    aria-label={`「${item.title}」的更多操作`}
                    aria-haspopup="menu"
                    aria-expanded={menuOpen}
                    className={`absolute right-1 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink-mute transition hover:bg-white hover:text-ink focus-visible:opacity-100 ${
                      menuOpen
                        ? "opacity-100"
                        : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    }`}
                  >
                    <MoreIcon />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {!collapsed && hiddenCount > 0 ? (
        <button
          type="button"
          onClick={onToggleExpanded}
          className="mt-0.5 w-full rounded-lg px-2 py-1 text-left text-[11px] font-medium text-ink-mute transition hover:bg-paper hover:text-accent"
        >
          {expanded ? "收起" : `显示更多（${hiddenCount}）`}
        </button>
      ) : null}
    </section>
  );
}
