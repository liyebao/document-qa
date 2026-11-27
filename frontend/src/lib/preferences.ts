import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

/**
 * 外观偏好（主题 + 字号）只影响当前浏览器，全部落在 localStorage：
 * - 主题默认浅色，用户在设置里切到深色后才记成 dark；
 * - 字号用比例表示，作用在根字号上（见 styles/index.css 的 --ui-font-scale），
 *   所以 rem 单位排版的文字与间距会一起等比缩放。
 */
export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "kb:theme";
export const FONT_SCALE_STORAGE_KEY = "kb:font-scale";

/** 与根字号相乘的比例：0.85 = 85%，1.4 = 140%。 */
export const FONT_SCALE_MIN = 0.85;
export const FONT_SCALE_MAX = 1.4;
export const FONT_SCALE_STEP = 0.05;
export const DEFAULT_FONT_SCALE = 1;
export const DEFAULT_THEME: ThemeMode = "light";

export const FONT_SCALE_CSS_VAR = "--ui-font-scale";

const THEME_COLOR_META: Record<ThemeMode, string> = {
  light: "#FFFFFF",
  dark: "#0F1218",
};

/** 纯函数：把任意输入夹到合法范围并按步长取整，避免浮点尾巴写进界面。 */
export function normalizeFontScale(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_FONT_SCALE;
  }
  const clamped = Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, value));
  return Number((Math.round(clamped / FONT_SCALE_STEP) * FONT_SCALE_STEP).toFixed(2));
}

export function readTheme(): ThemeMode {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    // 隐私模式等场景下 localStorage 不可用，退回默认浅色。
    return DEFAULT_THEME;
  }
}

export function readFontScale(): number {
  try {
    const raw = window.localStorage.getItem(FONT_SCALE_STORAGE_KEY);
    return raw ? normalizeFontScale(Number(raw)) : DEFAULT_FONT_SCALE;
  } catch {
    return DEFAULT_FONT_SCALE;
  }
}

export function saveTheme(theme: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // 存不下只影响下次打开时的默认值
  }
}

export function saveFontScale(scale: number): void {
  try {
    window.localStorage.setItem(FONT_SCALE_STORAGE_KEY, String(normalizeFontScale(scale)));
  } catch {
    // 同上
  }
}

/** 把主题写到 <html data-theme>：CSS 变量与 color-scheme 一起切换。 */
export function applyTheme(theme: ThemeMode): void {
  if (typeof document === "undefined") {
    return;
  }
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  // 移动端地址栏跟着变色；没有该 meta 时静默跳过。
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", THEME_COLOR_META[theme]);
}

/** 把比例写到根节点，CSS 里 `font-size: calc(100% * var(--ui-font-scale))` 会接住它。 */
export function applyFontScale(scale: number): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.style.setProperty(
    FONT_SCALE_CSS_VAR,
    String(normalizeFontScale(scale)),
  );
}

/**
 * 主题是跨页面共享的状态：侧边栏快捷切换和设置页的「外观」卡片必须看到同一个值。
 * 用 useSyncExternalStore 而不是自定义事件，保证两处渲染同步且不依赖先后顺序。
 */
const themeListeners = new Set<() => void>();
let themeState: ThemeMode | undefined;

function getThemeState(): ThemeMode {
  // 首次读取时懒加载，避免模块求值早于 localStorage 可用时拿到错误值。
  if (themeState === undefined) {
    themeState = readTheme();
  }
  return themeState;
}

function subscribeTheme(listener: () => void): () => void {
  themeListeners.add(listener);
  return () => {
    themeListeners.delete(listener);
  };
}

function getServerTheme(): ThemeMode {
  return DEFAULT_THEME;
}

export function setThemeMode(theme: ThemeMode): void {
  if (getThemeState() === theme) {
    return;
  }
  themeState = theme;
  applyTheme(theme);
  saveTheme(theme);
  themeListeners.forEach((listener) => listener());
}

export function toggleThemeMode(): void {
  setThemeMode(getThemeState() === "dark" ? "light" : "dark");
}

export function useThemeMode(): ThemeMode {
  return useSyncExternalStore(subscribeTheme, getThemeState, getServerTheme);
}

/** 首屏启动时调用：避免用户在设置里选过深色后，刷新又闪回浅色。 */
export function initializePreferences(): void {
  applyTheme(readTheme());
  applyFontScale(readFontScale());
}

export interface AppPreferences {
  theme: ThemeMode;
  fontScale: number;
  setTheme: (theme: ThemeMode) => void;
  setFontScale: (scale: number) => void;
  resetAppearance: () => void;
}

/**
 * 设置页「外观」卡片用的组合状态：主题走共享 store，字号是当前页面的轻量状态。
 * 这样不需要引入全局 Provider，侧边栏也能和设置页保持同步。
 */
export function useAppPreferences(): AppPreferences {
  const theme = useThemeMode();
  const [fontScale, setFontScaleState] = useState<number>(readFontScale);

  useEffect(() => {
    applyFontScale(fontScale);
    saveFontScale(fontScale);
  }, [fontScale]);

  const setFontScale = useCallback((scale: number) => {
    setFontScaleState(normalizeFontScale(scale));
  }, []);

  const resetAppearance = useCallback(() => {
    setThemeMode(DEFAULT_THEME);
    setFontScaleState(DEFAULT_FONT_SCALE);
  }, []);

  return {
    theme,
    fontScale,
    setTheme: setThemeMode,
    setFontScale,
    resetAppearance,
  };
}
