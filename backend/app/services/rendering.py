"""把原文件重新解析成可阅读的 HTML，供前端抽屉内预览。

和入库流程的区别：入库关心"切成语义片段"，这里关心"尽量保留原文的排版"，
所以标题层级、表格、分页都会还原成 HTML 结构，而不是压成纯文本。

PDF 与图片不经过这里——浏览器能自己渲染，直接内嵌原文件更准确。
"""

import csv
import html
import io
import zipfile
from pathlib import Path

from app.services.parsers.base import ParseError

# iframe 内无法复用 Tailwind，样式内联在文档里，配色与主站保持一致。
_STYLE = """
:root { color-scheme: light; }
body {
  margin: 0; padding: 24px 28px 40px;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  font-size: 15px; line-height: 1.85; color: #172033; background: #fff;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.45; margin: 1.5em 0 .6em; color: #172033; }
h1 { font-size: 1.55em; } h2 { font-size: 1.32em; } h3 { font-size: 1.12em; }
h4, h5, h6 { font-size: 1em; }
p { margin: .75em 0; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 13px; }
th, td { border: 1px solid #e1e7f0; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f5f7fb; font-weight: 600; }
pre {
  white-space: pre-wrap; word-break: break-word; margin: .8em 0;
  font-family: ui-monospace, Consolas, "Microsoft YaHei", monospace; font-size: 13px;
}
.slide, .sheet { border-top: 2px solid #e1e7f0; padding-top: 18px; margin-top: 26px; }
.slide:first-child, .sheet:first-child { border-top: 0; padding-top: 0; margin-top: 0; }
.label { font-size: 12px; color: #71809a; margin: 0 0 6px; }
mark.__hit { background: #fde68a; padding: 0 2px; border-radius: 3px; }
"""

_HTML_SHELL = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8" /><title>{title}</title><style>{style}</style></head>
<body>{body}</body>
</html>"""

# 单份文档的渲染上限：预览用于核对，不需要把整本几百页的书都吐出来。
_MAX_ROWS = 800
_MAX_SLIDES = 200
_MAX_PARAGRAPHS = 3000


def _page(title: str, body: str) -> str:
    return _HTML_SHELL.format(title=html.escape(title), style=_STYLE, body=body)


def _heading_level(style_name: str) -> int:
    """Word 的标题样式既可能是 "Heading 1"，也可能是本地化的 "标题 1"。"""
    lowered = (style_name or "").lower()
    for prefix in ("heading", "标题"):
        if lowered.startswith(prefix):
            digits = "".join(char for char in lowered if char.isdigit())
            if digits:
                return min(int(digits), 6)
    return 0


def render_docx(path: Path) -> str:
    from docx import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = DocxDocument(str(path))
    parts: list[str] = []
    count = 0
    for child in document.element.body.iterchildren():
        count += 1
        if count > _MAX_PARAGRAPHS:
            parts.append("<p class='label'>（内容较长，仅显示前面部分）</p>")
            break
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _heading_level(paragraph.style.name if paragraph.style else "")
            if level:
                parts.append(f"<h{level}>{html.escape(text)}</h{level}>")
            else:
                parts.append(f"<p>{html.escape(text)}</p>")
        elif tag == "tbl":
            table = Table(child, document)
            rows: list[str] = []
            for row_index, row in enumerate(table.rows):
                cells = "".join(
                    f"<{'th' if row_index == 0 else 'td'}>{html.escape(cell.text.strip())}</{'th' if row_index == 0 else 'td'}>"
                    for cell in row.cells
                )
                rows.append(f"<tr>{cells}</tr>")
            if rows:
                parts.append(f"<table>{''.join(rows)}</table>")
    return _page(path.stem, "".join(parts))


def render_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows: list[str] = []
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= _MAX_ROWS:
                    rows.append(
                        f"<tr><td colspan='{max(1, len(row))}' class='label'>（仅显示前 {_MAX_ROWS} 行）</td></tr>"
                    )
                    break
                if not any(cell not in (None, "") for cell in row):
                    continue
                cells = "".join(
                    f"<{'th' if index == 0 else 'td'}>{html.escape('' if cell is None else str(cell))}</{'th' if index == 0 else 'td'}>"
                    for cell in row
                )
                rows.append(f"<tr>{cells}</tr>")
            if not rows:
                continue
            parts.append(
                f"<section class='sheet'><p class='label'>工作表：{html.escape(sheet.title)}</p>"
                f"<table>{''.join(rows)}</table></section>"
            )
    finally:
        workbook.close()
    return _page(path.stem, "".join(parts))


def render_pptx(path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(str(path))
    parts: list[str] = []
    for index, slide in enumerate(presentation.slides, start=1):
        if index > _MAX_SLIDES:
            parts.append("<p class='label'>（幻灯片较多，仅显示前面部分）</p>")
            break
        texts: list[str] = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                line = "".join(run.text for run in paragraph.runs).strip()
                if line:
                    texts.append(f"<p>{html.escape(line)}</p>")
        body = "".join(texts) or "<p class='label'>（本页没有文本内容）</p>"
        parts.append(
            f"<section class='slide'><p class='label'>第 {index} 页</p>{body}</section>"
        )
    return _page(path.stem, "".join(parts))


def render_text(path: Path) -> str:
    """Markdown / TXT / CSV：原文就是文本，保留换行与缩进。"""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ParseError("文本编码无法识别，请使用 UTF-8 或 GB18030")
    return _page(path.stem, f"<pre>{html.escape(text)}</pre>")


def render_csv(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ParseError("CSV 编码无法识别，请使用 UTF-8 或 GB18030")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return _page(path.stem, "<p class='label'>（空文件）</p>")
    parts: list[str] = []
    for index, row in enumerate(rows[:_MAX_ROWS]):
        cells = "".join(
            f"<{'th' if index == 0 else 'td'}>{html.escape(cell)}</{'th' if index == 0 else 'td'}>"
            for cell in row
        )
        parts.append(f"<tr>{cells}</tr>")
    return _page(path.stem, f"<table>{''.join(parts)}</table>")


def render_epub(path: Path) -> str:
    """EPUB 按章取正文；只做纯文本呈现，不还原排版。"""
    parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xhtml")]
        for name in sorted(names)[:50]:
            try:
                chapter = archive.read(name).decode("utf-8", errors="ignore")
            except (KeyError, zipfile.BadZipFile):
                continue
            text = html.unescape(
                "".join(
                    char
                    for char in chapter
                    if char not in "<>"
                )
            )
            if text.strip():
                parts.append(f"<section class='sheet'><pre>{html.escape(text.strip())}</pre></section>")
    return _page(path.stem, "".join(parts) or "<p class='label'>（未能提取正文）</p>")


_RENDERERS = {
    "docx": render_docx,
    "xlsx": render_xlsx,
    "pptx": render_pptx,
    "md": render_text,
    "markdown": render_text,
    "txt": render_text,
    "csv": render_csv,
    "epub": render_epub,
}


def render_document(path: Path, file_format: str) -> str:
    """把原文件渲染成可读 HTML；不支持的格式抛出 ParseError。"""
    renderer = _RENDERERS.get(file_format)
    if renderer is None:
        raise ParseError("该格式暂不支持在线预览，请下载后查看")
    return renderer(path)
