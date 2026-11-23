import type { SearchItem, SearchKind } from "../api/search";

/**
 * 侧边栏搜索的纯逻辑单独放一个模块：
 * 组件文件只导出组件，才能让 react-refresh 的快速刷新保持有效。
 */

export const KIND_ORDER: readonly SearchKind[] = [
  "conversation",
  "document",
  "collection",
];

export const KIND_LABELS: Record<SearchKind, string> = {
  conversation: "对话",
  document: "文件",
  collection: "资料集",
};

export interface SearchKindGroup {
  kind: SearchKind;
  label: string;
  items: SearchItem[];
}

/**
 * 纯函数：把接口返回的混合结果按 kind 分成「对话 / 文件 / 资料集」三组，
 * 并丢掉空组，避免 UI 出现只有标题没有内容的空区块。
 */
export function groupSearchItems(items: SearchItem[]): SearchKindGroup[] {
  return KIND_ORDER.map((kind) => ({
    kind,
    label: KIND_LABELS[kind],
    items: items.filter((item) => item.kind === kind),
  })).filter((group) => group.items.length > 0);
}

/**
 * 纯函数：搜索结果点击后该去哪。
 * 对话进对话页；文件与资料集都落到资料集页，文件没有归属资料集时退回首页，
 * 保证任何一条结果都有确定的落点（不会出现点了没反应的死项）。
 */
export function searchItemPath(item: SearchItem): string {
  if (item.kind === "conversation") {
    return `/conversations/${item.id}`;
  }
  const collectionId = item.collection_id || (item.kind === "collection" ? item.id : "");
  return collectionId ? `/collections/${collectionId}` : "/";
}

/** 纯函数：键盘上下移动时的索引推进，带环绕，保证不会越界。 */
export function stepIndex(current: number, delta: number, length: number): number {
  if (length <= 0) {
    return -1;
  }
  if (current < 0) {
    return delta > 0 ? 0 : length - 1;
  }
  return (current + delta + length) % length;
}
