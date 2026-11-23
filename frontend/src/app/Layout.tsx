import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { NewConversationDialog } from "./NewConversationDialog";
import { useRecentConversations } from "./recent";
import { BrandMark, Sidebar } from "./Sidebar";
import { useFocusTrap } from "./useFocusTrap";

const SIDEBAR_COLLAPSED_KEY = "kb:sidebar-collapsed";
const SIDEBAR_WIDTH_EXPANDED = 272;
const SIDEBAR_WIDTH_COLLAPSED = 72;

/** 桌面侧边栏折叠偏好：读不到就当展开（首次访问的默认形态）。 */
function readSidebarCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * 应用外壳：左侧固定侧边栏 + 右侧主内容区。
 * 主内容区高度锁定一屏，页面自己决定滚动位置——对话页因此能把输入框
 * 稳定贴在主区域底部，资料集/设置页则在自己的滚动容器里正常滚动。
 */
export function AppLayout() {
  const { pathname } = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [newConversationOpen, setNewConversationOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed);
  const recent = useRecentConversations(pathname);
  const drawerPanelRef = useRef<HTMLDivElement>(null);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  const isConversation = /^\/conversations\/[^/]+/.test(pathname);
  const sidebarWidth = sidebarCollapsed
    ? SIDEBAR_WIDTH_COLLAPSED
    : SIDEBAR_WIDTH_EXPANDED;

  useFocusTrap(drawerPanelRef, drawerOpen, hamburgerRef);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const closeNewConversation = useCallback(() => setNewConversationOpen(false), []);
  const openNewConversation = useCallback(() => {
    setDrawerOpen(false);
    setNewConversationOpen(true);
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        // 存不下也不影响本次会话的折叠行为
      }
      return next;
    });
  }, []);

  // 路由变化后自动收起移动端抽屉。
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  // 打开抽屉后把焦点送进面板，避免键盘用户还停在背景内容里。
  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    const timer = window.setTimeout(() => {
      drawerPanelRef.current
        ?.querySelector<HTMLButtonElement>('button[aria-label="关闭导航"]')
        ?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [drawerOpen]);

  return (
    <div className="flex h-dvh overflow-hidden bg-paper">
      {/* 跳过导航：键盘/读屏用户可以一步越过整条侧边栏直达主内容。 */}
      <a href="#main-content" className="skip-link">
        跳到主要内容
      </a>

      <div
        className="hidden shrink-0 transition-[width] duration-200 ease-out md:block"
        style={{ width: sidebarWidth }}
      >
        <Sidebar
          pathname={pathname}
          recent={recent}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={toggleSidebar}
          onNewConversation={openNewConversation}
        />
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="关闭导航"
            onClick={closeDrawer}
            className="absolute inset-0 animate-fade cursor-default bg-ink/40 backdrop-blur-sm"
          />
          <div
            id="app-sidebar"
            ref={drawerPanelRef}
            role="dialog"
            aria-modal="true"
            aria-label="侧边导航"
            className="relative flex h-full w-[86%] max-w-[320px] animate-slide-in flex-col bg-white shadow-lift"
          >
            <Sidebar
              pathname={pathname}
              recent={recent}
              onNewConversation={openNewConversation}
              onNavigate={closeDrawer}
              onClose={closeDrawer}
            />
          </div>
        </div>
      )}

      {/*
        抽屉打开时把背景标记为 aria-hidden：屏幕阅读器不该读到被遮住的内容。
        焦点仍由 useFocusTrap 锁在抽屉里，这里只处理语义层。
      */}
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col"
        aria-hidden={drawerOpen ? true : undefined}
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-ink-line bg-white/95 px-3 py-2.5 backdrop-blur md:hidden">
          <button
            type="button"
            ref={hamburgerRef}
            onClick={() => setDrawerOpen(true)}
            aria-label="打开导航"
            aria-expanded={drawerOpen}
            aria-controls="app-sidebar"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-ink-soft transition hover:bg-paper hover:text-ink"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden="true"
              className="h-5 w-5"
            >
              <path d="M4 7h16M4 12h16M4 17h10" />
            </svg>
          </button>

          <div className="min-w-0 flex-1">
            <BrandMark compact />
          </div>

          <button
            type="button"
            onClick={openNewConversation}
            aria-label="新建对话"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-white shadow-sm transition hover:bg-accent-dark"
          >
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
          </button>
        </header>

        {/* tabIndex=-1：跳过导航链接指向这里后，键盘焦点真正落到主内容上而不是停在地址栏。 */}
        <main
          id="main-content"
          tabIndex={-1}
          className="flex min-h-0 flex-1 flex-col overflow-hidden focus:outline-none"
        >
          {isConversation ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <Outlet />
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 md:px-8 md:py-8">
                <Outlet />
              </div>
            </div>
          )}
        </main>
      </div>

      <NewConversationDialog
        open={newConversationOpen}
        collections={recent.collections}
        loading={recent.loading}
        error={recent.error}
        onClose={closeNewConversation}
      />
    </div>
  );
}
