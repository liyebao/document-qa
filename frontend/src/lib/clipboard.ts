/**
 * 复制文本到剪贴板。
 *
 * 非安全上下文（http 且非 localhost）没有 navigator.clipboard，或权限被拒时，
 * 回退到隐藏 textarea + execCommand，避免用户点了按钮却没有反应。
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // 权限被拒时继续尝试旧接口
    }
  }
  try {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.top = "0";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(helper);
    return ok;
  } catch {
    return false;
  }
}
