import { describe, expect, it } from "vitest";
import {
  RECENT_GROUP_LIMIT,
  formatActivityLabel,
  groupConversations,
  groupConversationsByCollection,
  isGroupCollapsed,
  parseCollapsedGroups,
  serializeCollapsedGroups,
  sortByRecentActivity,
  takeWithLimit,
  timeBucketOf,
  toggleCollapsedGroup,
  type RecentConversation,
} from "./recent";

const NOW = new Date(2026, 10, 24, 12, 0, 0);

function conversation(
  id: string,
  at: Date,
  collectionId = "collection-1",
): RecentConversation {
  return {
    id,
    collection_id: collectionId,
    title: `会话 ${id}`,
    created_at: at.toISOString(),
    collectionName: collectionId === "collection-1" ? "毕业设计调研" : "论文写作",
  };
}

function at(daysAgo: number, hour = 9): Date {
  return new Date(2026, 10, 24 - daysAgo, hour, 0, 0);
}

describe("groupConversations", () => {
  it("把会话按今天/昨天/近 7 天/更早分组并倒序排列", () => {
    const groups = groupConversations(
      [
        conversation("older", at(20)),
        conversation("week", at(4)),
        conversation("today-morning", at(0, 8)),
        conversation("yesterday", at(1)),
        conversation("today-noon", at(0, 11)),
      ],
      NOW,
    );

    expect(groups.map((group) => group.label)).toEqual([
      "今天",
      "昨天",
      "近 7 天",
      "更早",
    ]);
    expect(groups[0].items.map((item) => item.id)).toEqual([
      "today-noon",
      "today-morning",
    ]);
    expect(groups[1].items.map((item) => item.id)).toEqual(["yesterday"]);
    expect(groups[2].items.map((item) => item.id)).toEqual(["week"]);
    expect(groups[3].items.map((item) => item.id)).toEqual(["older"]);
  });

  it("隐藏空分组，并保留资料集名称", () => {
    const groups = groupConversations([conversation("only", at(0))], NOW);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("today");
    expect(groups[0].items[0].collectionName).toBe("毕业设计调研");
  });

  it("无法解析的时间归入更早，不丢失条目", () => {
    const broken: RecentConversation = {
      id: "broken",
      collection_id: "collection-1",
      title: "坏时间",
      created_at: "not-a-date",
      collectionName: "毕业设计调研",
    };

    const groups = groupConversations([broken], NOW);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("older");
    expect(groups[0].items[0].id).toBe("broken");
  });

  it("按最近活动时间分组：创建很久但今天刚说过话的会话算「今天」", () => {
    const revived: RecentConversation = {
      ...conversation("revived", at(30)),
      updated_at: at(0, 10).toISOString(),
    };

    const groups = groupConversations([revived], NOW);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("today");
  });

  it("空列表返回空数组", () => {
    expect(groupConversations([], NOW)).toEqual([]);
  });

  it("组上带条目数量，供组头显示", () => {
    const groups = groupConversations(
      [
        conversation("a", at(0, 8)),
        conversation("b", at(0, 9)),
        conversation("c", at(2)),
      ],
      NOW,
    );

    expect(groups.map((group) => group.count)).toEqual([2, 1]);
  });
});

describe("timeBucketOf", () => {
  it.each([
    [at(0, 7), "today"],
    [at(1, 23), "yesterday"],
    [at(2), "week"],
    [at(6, 23), "week"],
    [at(7), "older"],
  ])("%s 落在正确的桶里", (time, expected) => {
    expect(timeBucketOf(conversation("x", time as Date), NOW)).toBe(expected);
  });
});

describe("formatActivityLabel", () => {
  it("今天和昨天精确到分钟", () => {
    expect(formatActivityLabel(conversation("a", at(0, 9)), NOW)).toBe("今天 09:00");
    expect(formatActivityLabel(conversation("b", at(1, 21)), NOW)).toBe("昨天 21:00");
  });

  it("近 7 天用「N 天前」", () => {
    expect(formatActivityLabel(conversation("a", at(3)), NOW)).toBe("3 天前");
  });

  it("更早的显示月日，跨年补年份", () => {
    expect(formatActivityLabel(conversation("a", at(20)), NOW)).toBe("11 月 4 日");
    expect(formatActivityLabel(conversation("b", new Date(2025, 1, 3, 9)), NOW)).toBe(
      "2025 年 2 月 3 日",
    );
  });

  it("时间坏掉时给出可读文案而不是 Invalid Date", () => {
    const broken: RecentConversation = {
      id: "broken",
      collection_id: "collection-1",
      title: "坏时间",
      created_at: "not-a-date",
      collectionName: "毕业设计调研",
    };
    expect(formatActivityLabel(broken, NOW)).toBe("时间未知");
  });
});

describe("sortByRecentActivity", () => {
  it("不改动入参顺序", () => {
    const input = [conversation("a", at(3)), conversation("b", at(0))];
    const sorted = sortByRecentActivity(input);

    expect(sorted.map((item) => item.id)).toEqual(["b", "a"]);
    expect(input.map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("时间坏掉的条目排在最后", () => {
    const broken: RecentConversation = {
      id: "broken",
      collection_id: "collection-1",
      title: "坏时间",
      created_at: "not-a-date",
      collectionName: "毕业设计调研",
    };
    const sorted = sortByRecentActivity([broken, conversation("a", at(5))]);

    expect(sorted.map((item) => item.id)).toEqual(["a", "broken"]);
  });
});

describe("groupConversationsByCollection", () => {
  it("按资料集分组，组头带名称与数量，组间按最新活动排序", () => {
    const groups = groupConversationsByCollection(
      [
        conversation("paper-old", at(9), "collection-2"),
        conversation("paper-new", at(1), "collection-2"),
        conversation("design-new", at(0, 11), "collection-1"),
        conversation("design-old", at(0, 8), "collection-1"),
      ],
      NOW,
    );

    expect(groups.map((group) => group.label)).toEqual(["毕业设计调研", "论文写作"]);
    expect(groups.map((group) => group.count)).toEqual([2, 2]);
    expect(groups[0].items.map((item) => item.id)).toEqual(["design-new", "design-old"]);
    expect(groups[1].items.map((item) => item.id)).toEqual(["paper-new", "paper-old"]);
  });

  it("同一资料集的条目即使时间交错也聚在一起", () => {
    const groups = groupConversationsByCollection(
      [
        conversation("a1", at(0, 11), "collection-1"),
        conversation("b1", at(0, 10), "collection-2"),
        conversation("a2", at(0, 9), "collection-1"),
      ],
      NOW,
    );

    expect(groups).toHaveLength(2);
    expect(groups[0].items.map((item) => item.id)).toEqual(["a1", "a2"]);
  });

  it("缺少 collection_id 的会话归到「未归档资料集」，不会和真实资料集混淆", () => {
    const orphan: RecentConversation = {
      ...conversation("orphan", at(0, 8)),
      collection_id: "",
      collectionName: "",
    };
    const groups = groupConversationsByCollection(
      [orphan, conversation("a", at(1))],
      NOW,
    );

    // orphan 的活动时间更近，组头按最新活动排序时排在前面
    expect(groups.map((group) => group.key)).toEqual(["col:unknown", "col:collection-1"]);
    expect(groups[0].label).toBe("未归档资料集");
  });

  it("空列表返回空数组", () => {
    expect(groupConversationsByCollection([], NOW)).toEqual([]);
  });
});

describe("takeWithLimit", () => {
  it("超出上限时截断并给出隐藏数量", () => {
    const items = Array.from({ length: RECENT_GROUP_LIMIT + 4 }, (_, index) => index);
    const result = takeWithLimit(items, RECENT_GROUP_LIMIT);

    expect(result.visible).toHaveLength(RECENT_GROUP_LIMIT);
    expect(result.hiddenCount).toBe(4);
  });

  it("没超出上限时原样返回", () => {
    const result = takeWithLimit([1, 2], RECENT_GROUP_LIMIT);

    expect(result.visible).toEqual([1, 2]);
    expect(result.hiddenCount).toBe(0);
  });

  it("limit <= 0 视为不限制", () => {
    const result = takeWithLimit([1, 2, 3], 0);

    expect(result.visible).toEqual([1, 2, 3]);
    expect(result.hiddenCount).toBe(0);
  });
});

describe("折叠状态", () => {
  it("只序列化已折叠的分组", () => {
    const raw = serializeCollapsedGroups({
      "col:a": true,
      "col:b": false,
      "col:c": true,
    });

    expect(JSON.parse(raw)).toEqual(["col:a", "col:c"]);
  });

  it("解析数组与对象两种形态", () => {
    expect(parseCollapsedGroups(JSON.stringify(["col:a"]))).toEqual({ "col:a": true });
    expect(
      parseCollapsedGroups(JSON.stringify({ "col:a": true, "col:b": false })),
    ).toEqual({
      "col:a": true,
    });
  });

  it("坏数据与空值都回落到全部展开", () => {
    expect(parseCollapsedGroups(null)).toEqual({});
    expect(parseCollapsedGroups("")).toEqual({});
    expect(parseCollapsedGroups("{oops")).toEqual({});
    expect(parseCollapsedGroups("42")).toEqual({});
  });

  it("切换分组折叠状态返回新对象", () => {
    const initial = {};
    const collapsed = toggleCollapsedGroup(initial, "col:a");

    expect(collapsed).toEqual({ "col:a": true });
    expect(initial).toEqual({});
    expect(isGroupCollapsed(collapsed, "col:a")).toBe(true);
    expect(isGroupCollapsed(collapsed, "col:b")).toBe(false);
    expect(isGroupCollapsed(toggleCollapsedGroup(collapsed, "col:a"), "col:a")).toBe(
      false,
    );
  });

  it("序列化再解析可以还原", () => {
    const map = { "col:a": true };
    expect(parseCollapsedGroups(serializeCollapsedGroups(map))).toEqual(map);
  });
});
