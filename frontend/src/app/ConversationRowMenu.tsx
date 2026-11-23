import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface ConversationRowMenuProps {
  /** 触发按钮；用它定位菜单，同时判断点击是否落在菜单外。 */
  anchor: HTMLElement | null;
  title: string;
  onRename: () => void;
  onDelete: () => void;
  onClose: () => void;
}

const MENU_WIDTH = 132;
const MENU_HEIGHT = 84;

/**
 * 「…」菜单。用 portal + fixed 定位，而不是在列表行里绝对定位：
 * 侧边栏列表是滚动容器（overflow-y:auto），行内浮层会被滚动容器裁掉。
 */
export function ConversationRowMenu({
  anchor,
  title,
  onRename,
  onDelete,
  onClose,
}: ConversationRowMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!anchor) {
      return;
    }
    const rect = anchor.getBoundingClientRect();
    // 默认贴按钮下沿右对齐；下方空间不够就翻到上方，右侧越界就回收。
    const top =
      rect.bottom + MENU_HEIGHT + 8 > window.innerHeight
        ? rect.top - MENU_HEIGHT - 4
        : rect.bottom + 4;
    const left = Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8);
    setPosition({ top: Math.max(8, top), left: Math.max(8, left) });
  }, [anchor]);

  useEffect(() => {
    firstItemRef.current?.focus();

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || anchor?.contains(target)) {
        return;
      }
      onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        anchor?.focus();
      }
    };
    // 页面滚动或窗口尺寸变化后坐标系变了，直接收起比重新测量更稳。
    const handleDismiss = () => onClose();

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleDismiss, true);
    window.addEventListener("resize", handleDismiss);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleDismiss, true);
      window.removeEventListener("resize", handleDismiss);
    };
  }, [anchor, onClose]);

  if (!position) {
    return null;
  }

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={`「${title}」的更多操作`}
      style={{ top: position.top, left: position.left, width: MENU_WIDTH }}
      className="fixed z-[55] overflow-hidden rounded-xl border border-ink-line bg-paper py-1 shadow-lift"
    >
      <button
        ref={firstItemRef}
        type="button"
        role="menuitem"
        className="flex w-full items-center px-3 py-1.5 text-left text-[13px] text-ink transition hover:bg-paper-deep"
        onClick={onRename}
      >
        重命名
      </button>
      <button
        type="button"
        role="menuitem"
        className="flex w-full items-center px-3 py-1.5 text-left text-[13px] text-vermilion transition hover:bg-vermilion-wash"
        onClick={onDelete}
      >
        删除
      </button>
    </div>,
    document.body,
  );
}
