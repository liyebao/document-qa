"""HTML 文档解析。

优先用 trafilatura 抽正文（与网页导入共用 ``extract_markdown`` 的同一套参数），
再把抽出的 Markdown 交给 Markdown 分块器，从而复用同一套标题层级规则；
抽不出正文时退回纯标准库的块级切分。

与「网页导入」的关系：上传 HTML 存的是原始 .html 文件，抓取时保留标记；
网页导入 ``POST /collections/{id}/documents/url`` 存的是抓取 + 抽取后的 .md。
两条路径解析入口不同（parse_html 处理本地文件，网页导入直接把正文写入 .md），
但正文抽取参数一致，因此同一条链接用两种方式导入，检索结果应当一致。
"""

from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock
from app.services.parsers.html_text import (
    blocks_from_html,
    decode_html,
    extract_markdown,
)
from app.services.parsers.markdown import blocks_from_markdown_text


def parse_html(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else Path(data).read_bytes()
    html = decode_html(raw)
    if not html.strip():
        raise ParseError("HTML 文件为空")

    markdown = extract_markdown(html)
    blocks = blocks_from_markdown_text(markdown) if markdown.strip() else []
    if not blocks:
        blocks = blocks_from_html(html)
    if not blocks:
        raise ParseError("未从 HTML 中提取到正文（可能是纯脚本渲染的页面）")
    return blocks
