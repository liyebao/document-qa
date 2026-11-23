import { useEffect } from "react";
import type { RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 把键盘焦点锁在浮层内，关闭时把焦点还给触发元素。
 * 只处理 Tab/Shift+Tab；Escape 由各浮层自己决定是否关闭。
 */
export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  restoreRef?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!active) {
      return;
    }
    const container = containerRef.current;
    const previous =
      restoreRef?.current ?? (document.activeElement as HTMLElement | null);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !container) {
        return;
      }
      const items = [...container.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.getClientRects().length > 0,
      );
      if (items.length === 0) {
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;

      if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && current === first) {
        event.preventDefault();
        last.focus();
      } else if (!container.contains(current)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus?.();
    };
  }, [active, containerRef, restoreRef]);
}
