/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#FFFFFF",
          card: "#FFFFFF",
          deep: "#EEF2F8",
        },
        ink: {
          DEFAULT: "#172033",
          soft: "#4B5870",
          mute: "#5B6B84",
          line: "#E1E7F0",
        },
        accent: {
          DEFAULT: "#4F46E5",
          dark: "#4338CA",
          wash: "#EEF2FF",
        },
        vermilion: {
          DEFAULT: "#AF3B1F",
          dark: "#8C2C13",
          wash: "#F2E0D8",
        },
        jade: {
          DEFAULT: "#2E5B4C",
          wash: "#DFE9E3",
        },
        ochre: {
          DEFAULT: "#A8761F",
          wash: "#F3E9D5",
        },
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
