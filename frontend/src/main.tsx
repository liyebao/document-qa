import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app/App";
import { ErrorBoundary } from "./app/ErrorBoundary";
import { initializePreferences } from "./lib/preferences";
import "./styles/index.css";

// 渲染前先套用主题与字号：刷新后直接是用户上次选择的深色/字号，不闪一帧浅色。
initializePreferences();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
