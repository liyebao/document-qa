import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    build: {
      // rehype-highlight 自带 highlight.js 常用语言集，单包约 570 kB；
      // 本地部署的单页应用不做代码分割，把告警阈值调到实际水位之上。
      chunkSizeWarningLimit: 800,
    },
    server: {
      // 固定绑定 IPv4，避免 localhost 解析到 ::1 时与实际端口不一致
      host: env.VITE_DEV_HOST || "127.0.0.1",
      port: Number(env.VITE_DEV_PORT || 5173),
      // 端口被占用时直接失败，避免自动顺延到 5174 导致访问地址不一致
      strictPort: true,
      proxy: {
        "/api": {
          target: env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
