/**
 * 中文 Markdown 的常见"伪语法"修正。
 *
 * CommonMark 对强调符有边界要求：`**加粗**` 的闭合标记右侧必须是空白或标点。
 * 中文习惯写成 `**结论：**后面直接接正文`，闭合符右边是汉字，解析器不认，
 * 结果就是页面上真的显示两个星号。这里把这类不成立的标记直接去掉，保留文字；
 * 同时给缺空格的标题和列表补一个空格，让它们恢复成结构。
 */

const EMPHASIS = /\*\*([^*\n]+?)\*\*/g;

// 允许出现在强调符两侧的字符：空白、行首尾、括号、中文与英文标点。
const LEFT_OK = /[\s（(【「《：:，,。；;、]/;
const RIGHT_OK = /[\s）)】」》：:，,。；;、！？!?]/;

function tidyEmphasis(text: string): string {
  return text.replace(EMPHASIS, (match, inner: string, offset: number, whole: string) => {
    const before = offset === 0 ? "" : whole[offset - 1];
    const afterIndex = offset + match.length;
    const after = afterIndex >= whole.length ? "" : whole[afterIndex];
    const leftOk = before === "" || LEFT_OK.test(before);
    const rightOk = after === "" || RIGHT_OK.test(after);
    // 渲染不出来的标记只是噪音，去掉它反而更接近作者想表达的排版。
    return leftOk && rightOk ? match : inner;
  });
}

export function tidyMarkdown(text: string): string {
  let output = tidyEmphasis(text);
  // `#标题` / `-列表` 缺空格时不会被识别成标题和列表。
  output = output.replace(/^(#{1,6})(?=[^\s#])/gm, "$1 ");
  output = output.replace(/^( *)([-+])(?=[^\s])/gm, "$1$2 ");
  output = output.replace(/^( *)\*(?=[^*\s])/gm, "$1* ");
  return output;
}
