import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", end: true, index: "01", label: "我的资料集" },
  { to: "/settings/models", end: false, index: "02", label: "模型设置" },
];

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <span
        className={`flex items-center justify-center rounded-xl bg-accent font-sans font-bold leading-none text-white shadow-sm ${
          compact ? "h-8 w-8 text-base" : "h-10 w-10 text-lg"
        }`}
      >
        知
      </span>
      <span className="flex flex-col">
        <span
          className={`font-sans font-bold leading-tight text-ink ${
            compact ? "text-sm" : "text-[15px]"
          }`}
        >
          个人知识库
        </span>
        <span className="eyebrow mt-1">Knowledge Archive</span>
      </span>
    </span>
  );
}

export function AppLayout() {
  return (
    // 外壳固定为一屏高：主内容区自己滚动，会话页才能把输入框稳定停在底部。
    <div className="flex h-dvh flex-col overflow-hidden bg-paper md:flex-row">
      <aside className="hidden h-dvh w-[264px] shrink-0 flex-col justify-between border-r border-ink-line bg-white px-5 py-7 md:flex">
        <div>
          <NavLink to="/" aria-label="返回首页">
            <BrandMark />
          </NavLink>

          <nav className="mt-10 flex flex-col gap-1.5">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition duration-200 ease-out ${
                    isActive
                      ? "bg-accent-wash text-accent"
                      : "text-ink-soft hover:bg-paper hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs ${
                        isActive
                          ? "bg-white text-accent shadow-sm"
                          : "bg-paper text-ink-mute"
                      }`}
                    >
                      {item.index}
                    </span>
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="rounded-2xl bg-paper p-4">
          <p className="text-xs leading-relaxed text-ink-soft">
            本地单用户模式
            <br />
            资料和模型配置只保存在本机
          </p>
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-ink-line bg-white/95 backdrop-blur md:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <NavLink to="/" aria-label="返回首页">
              <BrandMark compact />
            </NavLink>
            <span className="rounded-lg bg-paper px-3 py-1.5 text-[11px] text-ink-mute">
              本地模式
            </span>
          </div>
          <nav className="flex gap-2 px-4 pb-3">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-xs font-medium transition ${
                    isActive
                      ? "bg-accent-wash text-accent"
                      : "text-ink-soft hover:bg-paper"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto flex min-h-0 w-full max-w-[1440px] flex-1 flex-col overflow-y-auto px-4 pb-10 pt-6 sm:px-6 md:px-8 md:pb-8 md:pt-8 xl:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
