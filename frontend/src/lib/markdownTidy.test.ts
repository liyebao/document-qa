import { describe, expect, it } from "vitest";
import { tidyMarkdown } from "./markdownTidy";

describe("markdown tidy", () => {
  it("keeps emphasis that ends before a punctuation mark", () => {
    expect(tidyMarkdown("- **进度风险**：需要提前准备")).toBe(
      "- **进度风险**：需要提前准备",
    );
  });

  it("drops emphasis markers that CommonMark refuses to parse", () => {
    expect(tidyMarkdown("**在干什么：**给后面七个环节准备落脚点")).toBe(
      "在干什么：给后面七个环节准备落脚点",
    );
  });

  it("keeps emphasis followed by whitespace", () => {
    expect(tidyMarkdown("**磁盘** 30GB 起步")).toBe("**磁盘** 30GB 起步");
  });

  it("adds the missing space after headings and list markers", () => {
    expect(tidyMarkdown("#把文档变成能提问的东西")).toBe("# 把文档变成能提问的东西");
    expect(tidyMarkdown("-第一项")).toBe("- 第一项");
    expect(tidyMarkdown("*斜体开头的中文行")).toBe("* 斜体开头的中文行");
  });

  it("leaves already-correct markdown untouched", () => {
    const source = "## 标题\n\n- 项目一\n- 项目二\n\n| 环节 | 产物 |\n|---|---|\n| 0 | 文件 |";
    expect(tidyMarkdown(source)).toBe(source);
  });
});
