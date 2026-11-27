/**
 * 色板全部走 CSS 变量（:root 定义浅色、[data-theme="dark"] 定义深色），
 * 这样切换主题不需要在每个组件里写 dark: 变体；`rgb(... / <alpha-value>)`
 * 的写法让 `bg-accent/10` 这类透明度修饰符继续可用。
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "rgb(var(--paper) / <alpha-value>)",
          card: "rgb(var(--paper-card) / <alpha-value>)",
          deep: "rgb(var(--paper-deep) / <alpha-value>)",
          sunken: "rgb(var(--paper-sunken) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          soft: "rgb(var(--ink-soft) / <alpha-value>)",
          mute: "rgb(var(--ink-mute) / <alpha-value>)",
          line: "rgb(var(--ink-line) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          dark: "rgb(var(--accent-dark) / <alpha-value>)",
          wash: "rgb(var(--accent-wash) / <alpha-value>)",
        },
        vermilion: {
          DEFAULT: "rgb(var(--vermilion) / <alpha-value>)",
          dark: "rgb(var(--vermilion-dark) / <alpha-value>)",
          wash: "rgb(var(--vermilion-wash) / <alpha-value>)",
        },
        jade: {
          DEFAULT: "rgb(var(--jade) / <alpha-value>)",
          wash: "rgb(var(--jade-wash) / <alpha-value>)",
        },
        ochre: {
          DEFAULT: "rgb(var(--ochre) / <alpha-value>)",
          wash: "rgb(var(--ochre-wash) / <alpha-value>)",
        },
      },
      /**
       * 10 ~ 15px 的少量字号原先写成任意值（text-[11px] 等），固定 px 不跟随
       * 根字号缩放；换成 rem 令牌后，设置里的「字号」滑杆才能整体生效。
       */
      fontSize: {
        "ui-2xs": "0.625rem",
        "ui-xs": "0.6875rem",
        "ui-sm": "0.8125rem",
        "ui-base": "0.9375rem",
      },
      fontFamily: {
        serif: [
          '"Source Han Sans SC"',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "system-ui",
          "sans-serif",
        ],
        sans: [
          '"Source Han Sans SC"',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          "system-ui",
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          '"Cascadia Mono"',
          "Consolas",
          "ui-monospace",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(23,32,51,0.04), 0 8px 24px -18px rgba(23,32,51,0.2)",
        lift: "0 8px 28px -16px rgba(23,32,51,0.24)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fade: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        blink: {
          "0%, 100%": { opacity: "0.25", transform: "translateY(0)" },
          "50%": { opacity: "1", transform: "translateY(-2px)" },
        },
        // 移动端抽屉从左侧滑入；位移很小，避免整屏横移带来的卡顿感。
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-14px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        // 自动消失提示条的剩余时间指示；实际时长由行内 animationDuration 控制。
        shrink: {
          "0%": { transform: "scaleX(1)" },
          "100%": { transform: "scaleX(0)" },
        },
      },
      animation: {
        rise: "rise 520ms cubic-bezier(0.22, 1, 0.36, 1) both",
        fade: "fade 380ms ease both",
        blink: "blink 1.2s ease-in-out infinite",
        "slide-in": "slideIn 240ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shrink: "shrink 1s linear forwards",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
