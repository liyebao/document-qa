import { describe, expect, it } from "vitest";
import type { SearchItem } from "../api/search";
import { groupSearchItems, searchItemPath, stepIndex } from "./sidebarSearchModel";

function item(
  overrides: Partial<SearchItem> & Pick<SearchItem, "kind" | "id">,
): SearchItem {
  return { label: `条目 ${overrides.id}`, ...overrides };
}

describe("groupSearchItems", () => {
  it("按 对话 / 文件 / 资料集 的固定顺序分组", () => {
    const groups = groupSearchItems([
      item({ kind: "collection", id: "c1" }),
      item({ kind: "conversation", id: "v1" }),
      item({ kind: "document", id: "d1" }),
    ]);

    expect(groups.map((group) => group.kind)).toEqual([
      "conversation",
      "document",
      "collection",
    ]);
    expect(groups.map((group) => group.label)).toEqual(["对话", "文件", "资料集"]);
  });

  it("丢掉没有结果的 kind，避免空标题", () => {
    const groups = groupSearchItems([item({ kind: "document", id: "d1" })]);

    expect(groups).toHaveLength(1);
    expect(groups[0].kind).toBe("document");
  });

  it("同一 kind 内的相对顺序保持不变", () => {
    const groups = groupSearchItems([
      item({ kind: "conversation", id: "v1" }),
      item({ kind: "conversation", id: "v2" }),
    ]);

    expect(groups[0].items.map((entry) => entry.id)).toEqual(["v1", "v2"]);
  });

  it("空数组返回空分组", () => {
    expect(groupSearchItems([])).toEqual([]);
  });
});

describe("searchItemPath", () => {
  it("对话进对话页", () => {
    expect(
      searchItemPath(item({ kind: "conversation", id: "conv-9", collection_id: "c1" })),
    ).toBe("/conversations/conv-9");
  });

  it("文件落到它所属的资料集页", () => {
    expect(
      searchItemPath(item({ kind: "document", id: "doc-7", collection_id: "col-3" })),
    ).toBe("/collections/col-3");
  });

  it("资料集优先用自己的 id，没有 collection_id 也不会跳错", () => {
    expect(searchItemPath(item({ kind: "collection", id: "col-5" }))).toBe(
      "/collections/col-5",
    );
  });

  it("文件没有归属资料集时退回首页，而不是拼出一个空 id 的链接", () => {
    expect(searchItemPath(item({ kind: "document", id: "doc-1" }))).toBe("/");
  });
});

describe("stepIndex", () => {
  it("无选中时向下从 0 开始、向上从末尾开始", () => {
    expect(stepIndex(-1, 1, 3)).toBe(0);
    expect(stepIndex(-1, -1, 3)).toBe(2);
  });

  it("首尾环绕", () => {
    expect(stepIndex(2, 1, 3)).toBe(0);
    expect(stepIndex(0, -1, 3)).toBe(2);
  });

  it("空结果返回 -1", () => {
    expect(stepIndex(-1, 1, 0)).toBe(-1);
  });
});
