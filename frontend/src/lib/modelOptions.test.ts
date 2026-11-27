import { describe, expect, it } from "vitest";
import {
  buildModelOptions,
  countUnlistedModels,
  normalizeModelName,
} from "./modelOptions";

describe("model options", () => {
  it("keeps the catalog order and marks the first as recommended when未探测", () => {
    const options = buildModelOptions(["bge-m3", "nomic-embed-text"], null);

    expect(options).toEqual([
      { value: "bge-m3", installed: false, recommended: true },
      { value: "nomic-embed-text", installed: false, recommended: false },
    ]);
  });

  it("treats bge-m3:latest as the same model as bge-m3", () => {
    const options = buildModelOptions(["bge-m3", "nomic-embed-text"], ["bge-m3:latest"]);

    expect(options.map((item) => item.value)).toEqual(["bge-m3", "nomic-embed-text"]);
    expect(options[0].installed).toBe(true);
    expect(options[1].installed).toBe(false);
  });

  it("puts installed models first and keeps uninstalled ones selectable", () => {
    const options = buildModelOptions(
      ["qwen3:4b", "qwen3:8b", "llama3.3:70b"],
      ["llama3.3:70b"],
    );

    expect(options.map((item) => item.value)).toEqual([
      "llama3.3:70b",
      "qwen3:4b",
      "qwen3:8b",
    ]);
    expect(options.filter((item) => item.installed)).toHaveLength(1);
  });

  it("does not mix models outside the catalog into the dropdown", () => {
    // qwen3:4b 是本地已装的聊天模型，不能出现在"检索模型"下拉里。
    const options = buildModelOptions(["bge-m3"], ["bge-m3:latest", "qwen3:4b"]);

    expect(options.map((item) => item.value)).toEqual(["bge-m3"]);
    expect(countUnlistedModels(["bge-m3:latest", "qwen3:4b"], [["bge-m3"]])).toBe(1);
  });

  it("normalizes only the latest tag", () => {
    expect(normalizeModelName("bge-m3:latest")).toBe("bge-m3");
    expect(normalizeModelName("qwen3:4b")).toBe("qwen3:4b");
    expect(normalizeModelName("qwen3-embedding:0.6b")).toBe("qwen3-embedding:0.6b");
  });
});
