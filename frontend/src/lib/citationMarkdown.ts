/**
 * 引用编号与 Markdown 的桥接工具。
 *
 * 后端返回的回答里引用是裸的 [编号]，直接交给 Markdown 解析会被当作引用式链接语法。
 * 这里先把它改写成 [编号](cite:编号) 的行内链接，渲染时再按 cite: 协议识别。
 */
export const CITATION_SCHEME = "cite:";

// 已经是 [编号](...) 的写法不再重复改写，避免二次包装。
const CITATION_PATTERN = /\[(\d+)\](?!\()/g;

export function toCitationLinks(content: string): string {
  return content.replace(
    CITATION_PATTERN,
    (_match, index: string) => `[${index}](${CITATION_SCHEME}${index})`,
  );
}

/** 从 cite: 链接里取出引用编号；不是引用链接时返回 null。 */
export function citationMarkerFromHref(href: string): number | null {
  if (!href.startsWith(CITATION_SCHEME)) {
    return null;
  }
  const marker = Number(href.slice(CITATION_SCHEME.length));
  return Number.isInteger(marker) && marker > 0 ? marker : null;
}
