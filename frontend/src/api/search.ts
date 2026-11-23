import { request } from "./client";

export type SearchKind = "conversation" | "document" | "collection";

/** 全局搜索的单条结果；`collection_id` 既是跳转目标，也是结果的上下文。 */
export interface SearchItem {
  kind: SearchKind;
  id: string;
  label: string;
  sublabel?: string | null;
  collection_id?: string | null;
  collection_name?: string | null;
}

export interface SearchResponse {
  items: SearchItem[];
}

/** 每类最多返回多少条：侧边栏空间有限，够用即可。 */
export const SEARCH_PER_KIND = 5;

export function searchAll(
  query: string,
  perKind: number = SEARCH_PER_KIND,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, per_kind: String(perKind) });
  return request<SearchResponse>(`/search?${params.toString()}`, { timeoutMs: 15000 });
}
