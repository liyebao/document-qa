import {
  DEFAULT_FONT_SCALE,
  FONT_SCALE_MAX,
  FONT_SCALE_MIN,
  FONT_SCALE_STEP,
  type AppPreferences,
  type ThemeMode,
} from "../lib/preferences";

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

/** 正文基准字号（text-sm = 0.875rem = 14px），用来把比例换算成实际像素展示。 */
const BASE_BODY_FONT_PX = 14;

interface Props {
  preferences: AppPreferences;
}

/** 设置页的「外观」卡片：主题切换 + 字号滑杆，改动即时生效并写入 localStorage。 */
export function AppearanceSettings({ preferences }: Props) {
  const { theme, fontScale, setTheme, setFontScale, resetAppearance } = preferences;
  const percent = Math.round(fontScale * 100);
  const isDefault = theme === "light" && fontScale === DEFAULT_FONT_SCALE;
  // 滑杆左侧已选中的部分用主题色填充，右侧用底色，比原生滑轨更容易看出当前比例。
  const fill = ((fontScale - FONT_SCALE_MIN) / (FONT_SCALE_MAX - FONT_SCALE_MIN)) * 100;
  // 默认 100% 在 85%–140% 区间里的真实位置（占比 0–100），刻度与刻度文字共用同一个值。
  const defaultPosition =
    ((DEFAULT_FONT_SCALE - FONT_SCALE_MIN) / (FONT_SCALE_MAX - FONT_SCALE_MIN)) * 100;

  return (
    <section className="surface mt-4 p-5 sm:p-6" aria-labelledby="appearance-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="appearance-heading" className="text-base font-semibold text-ink sm:text-lg">
            外观
          </h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-ink-soft">
            主题与字号只保存在当前浏览器。默认浅色模式、100% 字号。
          </p>
        </div>
        <button
          type="button"
          onClick={resetAppearance}
          disabled={isDefault}
          className="row-action shrink-0 disabled:cursor-not-allowed disabled:opacity-40"
        >
          恢复默认
        </button>
      </div>

      <div className="mt-5 grid gap-6 sm:grid-cols-2">
        <div>
          <p id="theme-label" className="text-sm font-medium text-ink">
            主题
          </p>
          <div
            role="group"
            aria-labelledby="theme-label"
            className="mt-2 inline-flex rounded-xl border border-ink-line bg-paper-deep p-1"
          >
            {THEME_OPTIONS.map((option) => {
              const active = theme === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setTheme(option.value)}
                  aria-pressed={active}
                  className={`rounded-lg px-5 py-1.5 text-sm font-medium transition duration-200 ease-out ${
                    active
                      ? "bg-accent-wash text-accent shadow-sm"
                      : "text-ink-mute hover:text-ink"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs leading-5 text-ink-mute">
            默认浅色模式；深色更适合夜间阅读。
          </p>
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-2">
            <label htmlFor="font-scale" className="text-sm font-medium text-ink">
              字号
            </label>
            <div className="flex items-baseline gap-2">
              {/* 把百分比换算成看得见的像素，避免「拖了滑杆但没感觉字变大」。 */}
              <span className="text-xs tabular-nums text-ink-mute">
                正文约 {Math.round(BASE_BODY_FONT_PX * fontScale)}px
              </span>
              <span className="text-sm font-semibold tabular-nums text-accent">
                {percent}%
              </span>
            </div>
          </div>
          <div className="relative mt-3">
            <input
              id="font-scale"
              type="range"
              min={FONT_SCALE_MIN}
              max={FONT_SCALE_MAX}
              step={FONT_SCALE_STEP}
              value={fontScale}
              onChange={(event) => setFontScale(Number(event.target.value))}
              aria-describedby="font-scale-hint"
              className="range-slider"
              style={{
                backgroundImage: `linear-gradient(to right, rgb(var(--accent)) ${fill}%, rgb(var(--paper-deep)) ${fill}%)`,
              }}
            />
            {/* 默认值刻度：给「100%」一个视觉锚点，拖到 110% 时就不会误以为还在默认位置。 */}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute top-0 h-1.5 w-0.5 -translate-x-1/2 rounded-full bg-paper-card"
              style={{ left: `${defaultPosition}%` }}
            />
          </div>
          {/*
            刻度必须按真实比例摆放：100% 落在 85%–140% 区间的 27.3% 处，
            用 justify-between 平均分配会让 110% 的滑块看起来正对「默认 100%」。
          */}
          <div
            id="font-scale-hint"
            className="relative mt-2 h-4 text-xs tabular-nums text-ink-mute"
          >
            {/* 视觉刻度按真实比例摆放，读屏用一句完整描述代替三个孤立数字。 */}
            <span className="sr-only">
              字号范围 {Math.round(FONT_SCALE_MIN * 100)}% 到{" "}
              {Math.round(FONT_SCALE_MAX * 100)}%，默认{" "}
              {Math.round(DEFAULT_FONT_SCALE * 100)}%，当前 {percent}%
            </span>
            <span aria-hidden="true" className="absolute left-0 top-0">
              {Math.round(FONT_SCALE_MIN * 100)}%
            </span>
            <span
              aria-hidden="true"
              className="absolute top-0 -translate-x-1/2 whitespace-nowrap"
              style={{ left: `${defaultPosition}%` }}
            >
              {Math.round(DEFAULT_FONT_SCALE * 100)}%
            </span>
            <span aria-hidden="true" className="absolute right-0 top-0">
              {Math.round(FONT_SCALE_MAX * 100)}%
            </span>
          </div>
        </div>
      </div>

      <p className="mt-5 rounded-xl border border-dashed border-ink-line px-3.5 py-2.5 text-sm leading-6 text-ink-soft">
        预览：把资料放进资料集，提问时用引用回到原文核对答案。
      </p>
    </section>
  );
}
