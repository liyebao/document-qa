import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listCollections } from "../api/collections";
import { errorMessage } from "../api/client";
import { listRecentConversations } from "../api/conversations";
import type { CollectionSummary, ConversationSummary } from "../api/types";

/**
 * 侧边栏「最近」走一次 `GET /api/conversations` 取回跨资料集的会话，
 * 增删资料集/会话后通过一个自定义事件通知侧边栏重新拉取，
 * 避免为了刷新导航去改动路由或提升整页状态。
 */
const CONVERSATIONS_CHANGED_EVENT = "kb:conversations-changed";

export function notifyConversationsChanged(): void {
  window.dispatchEvent(new Event(CONVERSATIONS_CHANGED_EVENT));
}

/**
 * 侧边栏重命名只影响列表，当前正在看的会话页标题不会随路由变化刷新，
 * 因此额外广播一次「某会话改了名」，由对话页自己更新标题。
 */
const CONVERSATION_RENAMED_EVENT = "kb:conversation-renamed";

export interface ConversationRenamedDetail {
  id: string;
  title: string;
}

export function notifyConversationRenamed(id: string, title: string): void {
  window.dispatchEvent(
    new CustomEvent<ConversationRenamedDetail>(CONVERSATION_RENAMED_EVENT, {
      detail: { id, title },
    }),
  );
}

/** 订阅重命名事件；返回取消订阅函数，方便在 effect 清理里调用。 */
export function subscribeConversationRenamed(
  handler: (detail: ConversationRenamedDetail) => void,
): () => void {
  const listener = (event: Event) => {
    handler((event as CustomEvent<ConversationRenamedDetail>).detail);
  };
  window.addEventListener(CONVERSATION_RENAMED_EVENT, listener);
  return () => window.removeEventListener(CONVERSATION_RENAMED_EVENT, listener);
}

export interface RecentConversation extends ConversationSummary {
  collectionName: string;
  /** 最近活动时间；`GET /api/conversations` 返回，缺省时回退 created_at。 */
  updated_at?: string;
}

/** 时间口径与列表原有的「今天 / 昨天 / 近 7 天 / 更早」一致。 */
export type RecentTimeBucket = "today" | "yesterday" | "week" | "older";

export const TIME_BUCKET_ORDER: readonly RecentTimeBucket[] = [
  "today",
  "yesterday",
  "week",
  "older",
];

export const TIME_BUCKET_LABELS: Record<RecentTimeBucket, string> = {
  today: "今天",
  yesterday: "昨天",
  week: "近 7 天",
  older: "更早",
};

export interface RecentGroup {
  key: RecentTimeBucket;
  label: string;
  count: number;
  items: RecentConversation[];
}

export interface RecentCollectionGroup {
  /** 折叠状态的持久化键，形如 `col:<collection_id>`。 */
  key: string;
  collectionId: string | null;
  label: string;
  count: number;
  items: RecentConversation[];
}

/** 每组默认渲染条数；超出的部分折叠在「显示更多」后面，控制 DOM 规模。 */
export const RECENT_GROUP_LIMIT = 6;

const DAY_MS = 24 * 60 * 60 * 1000;
const UNKNOWN_COLLECTION_NAME = "未归档资料集";

/** 最近活动时间优先（有消息时间就用它），否则回退创建时间。 */
function activityTime(item: RecentConversation): number {
  return Date.parse(item.updated_at ?? item.created_at);
}

function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

/** 纯函数：单条会话落在哪个时间桶；时间无法解析时归入「更早」，不丢条目。 */
export function timeBucketOf(
  item: RecentConversation,
  now: Date = new Date(),
): RecentTimeBucket {
  const activity = activityTime(item);
  if (Number.isNaN(activity)) {
    return "older";
  }
  const today = startOfDay(now);
  const days = Math.round((today - startOfDay(new Date(activity))) / DAY_MS);
  if (days <= 0) {
    return "today";
  }
  if (days === 1) {
    return "yesterday";
  }
  return days < 7 ? "week" : "older";
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * 纯函数：单条会话的行内时间标签。
 * 与分组口径同源（今天 / 昨天 / 近 7 天 / 更早），只是把桶名换成更精确的表达，
 * 这样按资料集分组时也不会丢掉「什么时候聊的」这个信息。
 */
export function formatActivityLabel(
  item: RecentConversation,
  now: Date = new Date(),
): string {
  const activity = activityTime(item);
  if (Number.isNaN(activity)) {
    return "时间未知";
  }
  const bucket = timeBucketOf(item, now);
  const date = new Date(activity);
  if (bucket === "today" || bucket === "yesterday") {
    return `${TIME_BUCKET_LABELS[bucket]} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }
  if (bucket === "week") {
    const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
    return `${days} 天前`;
  }
  const sameYear = date.getFullYear() === now.getFullYear();
  const monthDay = `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  return sameYear ? monthDay : `${date.getFullYear()} 年 ${monthDay}`;
}

/** 纯函数：按最近活动时间倒序；时间解析失败的条目排在最后而不是打乱顺序。 */
export function sortByRecentActivity(items: RecentConversation[]): RecentConversation[] {
  const score = (item: RecentConversation) => {
    const time = activityTime(item);
    return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
  };
  return [...items].sort((left, right) => score(right) - score(left));
}

/**
 * 纯函数：按「今天 / 昨天 / 近 7 天 / 更早」分组，组内按最近活动时间倒序。
 * 单独抽出来是为了能在 vitest 里直接验证分组边界，而不必渲染整个布局。
 */
export function groupConversations(
  items: RecentConversation[],
  now: Date = new Date(),
): RecentGroup[] {
  const buckets = new Map<RecentTimeBucket, RecentConversation[]>(
    TIME_BUCKET_ORDER.map((key) => [key, []]),
  );

  for (const item of sortByRecentActivity(items)) {
    buckets.get(timeBucketOf(item, now))?.push(item);
  }

  return TIME_BUCKET_ORDER.map((key) => ({
    key,
    label: TIME_BUCKET_LABELS[key],
    count: buckets.get(key)?.length ?? 0,
    items: buckets.get(key) ?? [],
  })).filter((group) => group.items.length > 0);
}

/**
 * 纯函数：按资料集分组，组头显示资料集名与数量。
 * 组间顺序取组内最新活动时间（最近说过的资料集排在前面），组内同样按活动时间倒序。
 */
export function groupConversationsByCollection(
  items: RecentConversation[],
  now: Date = new Date(),
): RecentCollectionGroup[] {
  const groups = new Map<string, RecentCollectionGroup>();

  for (const item of sortByRecentActivity(items)) {
    const collectionId = item.collection_id || null;
    const key = `col:${collectionId ?? "unknown"}`;
    const group = groups.get(key);
    if (group) {
      group.items.push(item);
      group.count += 1;
      continue;
    }
    groups.set(key, {
      key,
      collectionId,
      label: item.collectionName?.trim() || UNKNOWN_COLLECTION_NAME,
      count: 1,
      items: [item],
    });
  }

  // 条目已全局倒序，组的插入顺序即最新活动顺序；这里显式再排一次，
  // 避免上游数据顺序变化时组头顺序跟着乱。
  const score = (group: RecentCollectionGroup) => {
    const time = activityTime(group.items[0]);
    return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
  };

  void now;
  return [...groups.values()].sort((left, right) => score(right) - score(left));
}

/**
 * 纯函数：每组只渲染前 `limit` 条，其余折叠。
 * `limit <= 0` 视为不限制，方便以后调整而不改调用点。
 */
export function takeWithLimit<T>(
  items: T[],
  limit: number,
): { visible: T[]; hiddenCount: number } {
  if (limit <= 0 || items.length <= limit) {
    return { visible: items, hiddenCount: 0 };
  }
  return { visible: items.slice(0, limit), hiddenCount: items.length - limit };
}

export type CollapsedGroupMap = Record<string, boolean>;

/**
 * 纯函数：解析 localStorage 里的折叠状态。
 * 兼容两种历史写法（数组存 key / 对象存布尔），坏数据一律当作「全部展开」，
 * 侧边栏不该因为一段脏字符串就报错。
 */
export function parseCollapsedGroups(raw: string | null): CollapsedGroupMap {
  if (!raw) {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.reduce<CollapsedGroupMap>((accumulator, key) => {
        if (typeof key === "string" && key) {
          accumulator[key] = true;
        }
        return accumulator;
      }, {});
    }
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed as Record<string, unknown>).reduce<CollapsedGroupMap>(
        (accumulator, [key, value]) => {
          if (value === true) {
            accumulator[key] = true;
          }
          return accumulator;
        },
        {},
      );
    }
  } catch {
    // 非法 JSON：忽略记忆，回落到默认展开
  }
  return {};
}

/** 纯函数：只序列化「已折叠」的键，数据量最小。 */
export function serializeCollapsedGroups(map: CollapsedGroupMap): string {
  return JSON.stringify(Object.keys(map).filter((key) => map[key]));
}

/** 纯函数：折叠/展开单个分组，返回新对象（便于 React 状态比较）。 */
export function toggleCollapsedGroup(
  map: CollapsedGroupMap,
  key: string,
): CollapsedGroupMap {
  const next = { ...map };
  if (next[key]) {
    delete next[key];
  } else {
    next[key] = true;
  }
  return next;
}

export function isGroupCollapsed(map: CollapsedGroupMap, key: string): boolean {
  return map[key] === true;
}

export interface RecentConversationsState {
  collections: CollectionSummary[];
  items: RecentConversation[];
  groups: RecentGroup[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * `refreshKey` 传入当前 pathname：创建会话、切换页面后侧边栏都能拿到新列表。
 */
export function useRecentConversations(refreshKey: string): RecentConversationsState {
  const [collections, setCollections] = useState<CollectionSummary[]>([]);
  const [items, setItems] = useState<RecentConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const requestSeq = useRef(0);
  // 同一时刻只保留一个在途请求：重命名/删除时先广播再手动刷新，
  // 两路调用会共用这次请求，避免为了刷新列表多打一次接口。
  const inFlight = useRef<Promise<void> | null>(null);

  const refresh = useCallback((): Promise<void> => {
    if (inFlight.current) {
      return inFlight.current;
    }
    // 用序号守卫丢弃过期响应：路由快速切换时旧响应不能覆盖新响应。
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    const task = (async () => {
      try {
        const [collectionList, recent] = await Promise.all([
          listCollections(),
          listRecentConversations(),
        ]);
        if (seq !== requestSeq.current) {
          return;
        }
        setCollections(collectionList);
        setItems(
          recent.map<RecentConversation>((item) => ({
            ...item,
            collectionName: item.collection_name,
          })),
        );
        setError(null);
      } catch (err) {
        if (seq !== requestSeq.current) {
          return;
        }
        setError(errorMessage(err));
      } finally {
        if (seq === requestSeq.current) {
          setLoading(false);
        }
        inFlight.current = null;
      }
    })();
    inFlight.current = task;
    return task;
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  useEffect(() => {
    const handler = () => {
      void refresh();
    };
    window.addEventListener(CONVERSATIONS_CHANGED_EVENT, handler);
    return () => window.removeEventListener(CONVERSATIONS_CHANGED_EVENT, handler);
  }, [refresh]);

  const groups = useMemo(() => groupConversations(items), [items]);

  return { collections, items, groups, loading, error, refresh };
}
