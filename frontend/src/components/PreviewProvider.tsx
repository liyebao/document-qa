import {
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation } from "react-router-dom";
import {
  PreviewContext,
  type PreviewRequest,
  type PreviewContextValue,
} from "../lib/previewContext";
import { DocumentPreviewPanel } from "./DocumentPreviewPanel";

// 两侧最小宽度，避免把任意一边拖成看不见。
const MIN_PANEL = 320;
const MIN_MAIN = 360;

/**
 * 全局预览面板：引用卡片和文件列表都通过 usePreview 打开同一块面板。
 *
 * 桌面端做成左右分栏（对话在左、原文在右），中间的分隔条可以拖动调整比例；
 * 面板自身在 md 以下会退化成全屏浮层，见 DocumentPreviewPanel。
 */
export function PreviewProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<PreviewRequest | null>(null);
  // 只存在组件状态里：同一个对话内反复打开沿用宽度，离开页面即恢复默认。
  const [panelWidth, setPanelWidth] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const { pathname } = useLocation();

  const openPreview = useCallback((next: PreviewRequest) => {
    setRequest(next);
  }, []);
  const closePreview = useCallback(() => {
    setRequest(null);
  }, []);

  // Provider 在 Layout 内不会随路由卸载：原文和它专属的分栏比例都属于当前页面，
  // 换会话/换页面时一起重置，回到旧对话看到的是默认布局。
  useEffect(() => {
    closePreview();
    setPanelWidth(null);
  }, [pathname, closePreview]);

  const value = useMemo<PreviewContextValue>(
    () => ({ openPreview, closePreview }),
    [openPreview, closePreview],
  );

  const handlePointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    // 拖动期间固定光标并禁用选中，否则会连同正文一起被选中。
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    if (!dragging.current || !container) {
      return;
    }
    const rect = container.getBoundingClientRect();
    const wanted = rect.right - event.clientX;
    const max = Math.max(MIN_PANEL, rect.width - MIN_MAIN);
    setPanelWidth(Math.min(Math.max(wanted, MIN_PANEL), max));
  }, []);

  const stopDragging = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  const resetWidth = useCallback(() => {
    setPanelWidth(null);
  }, []);

  const layoutStyle = {
    "--preview-width": panelWidth === null ? "min(720px, 46%)" : `${panelWidth}px`,
  } as CSSProperties;

  return (
    <PreviewContext.Provider value={value}>
      <div ref={containerRef} className="flex min-h-0 flex-1 gap-2" style={layoutStyle}>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>

        {request ? (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="拖动调整原文与对话的宽度，双击恢复默认"
            title="拖动调整宽度，双击恢复默认"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={stopDragging}
            onPointerCancel={stopDragging}
            onDoubleClick={resetWidth}
            className="group hidden w-1.5 shrink-0 cursor-col-resize touch-none items-center justify-center rounded-full transition hover:bg-accent/10 md:flex"
          >
            <span className="h-10 w-1 rounded-full bg-ink-line transition group-hover:bg-accent/60" />
          </div>
        ) : null}

        <DocumentPreviewPanel request={request} onClose={closePreview} />
      </div>
    </PreviewContext.Provider>
  );
}
