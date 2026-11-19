import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.services.parsers.base import ParseError, TextBlock, normalize_text

# 只识别“编号型”标题：第X章/节、一、、（一）、1.2/1.2.3、附录。
# 没有编号、只靠字号区分的版式交给后续字体分析，不在正则里猜。
_CHAPTER = re.compile(r"^第\s*[〇零一二三四五六七八九十百千0-9]+\s*(章|节|篇|部分)\s*\S*")
_APPENDIX = re.compile(r"^附\s*录\s*[A-Za-z〇零一二三四五六七八九十0-9]*\s*\S*")
_CN_TOP = re.compile(r"^[一二三四五六七八九十]+\s*[、.．]\s*\S+")
_CN_SUB = re.compile(r"^[（(][一二三四五六七八九十]+[）)]\s*\S+")
_NUM_MULTI = re.compile(r"^(\d+(?:\.\d+){1,3})\s*[、.．]?\s*(\S.*)$")
_NUM_SINGLE = re.compile(r"^(\d+)\s*[、.．]\s*(\S.*)$")
_NUM_SPACE = re.compile(r"^(\d+)\s+(\S.*)$")
_PAGE_NUMBER = re.compile(r"^[-—–\s]*\d{1,4}[-—–\s]*$")
_PAGE_NUMBER_CN = re.compile(r"^第\s*\d+\s*页(?:\s*[/／]\s*共\s*\d+\s*页)?$")
_SENTENCE_MARKS = "。！？；"


def _heading_for(line: str, stack: list[tuple[int, str]]) -> tuple[int, str] | None:
    """判断一行是否是标题，返回 (层级, 标题文本)。

    ``stack`` 是当前标题栈，用来处理“第一章”下面的“一、”“（一）”这类
    相对层级；层级只影响标题路径的裁剪，不影响正文。
    """
    text = line.strip()
    if not text or len(text) > 60:
        return None
    if any(mark in text for mark in _SENTENCE_MARKS):
        return None
    if text.endswith(("，", ",", "、", "：", ":")):
        return None

    chapter = _CHAPTER.match(text)
    if chapter:
        return (2 if chapter.group(1) == "节" else 1), text
    if _APPENDIX.match(text):
        return 1, text
    if _CN_TOP.match(text):
        level = 2 if any(lv == 1 for lv, _ in stack) else 1
        return level, text
    if _CN_SUB.match(text):
        level = max((lv for lv, _ in stack), default=0) + 1
        return level, text

    multi = _NUM_MULTI.match(text)
    if multi:
        return min(multi.group(1).count(".") + 1, 4), text
    single = _NUM_SINGLE.match(text) or _NUM_SPACE.match(text)
    if single:
        title = single.group(2)
        # 单级数字标题最容易和有序列表混淆：要求短、不带句读。
        if len(title) <= 30 and not any(mark in title for mark in "，,；;：:"):
            return 1, text
    return None


def _blocks_from_page(
    text: str, page_number: int, stack: list[tuple[int, str]]
) -> list[TextBlock]:
    """把一页文本按标题边界切成多个块，标题路径写在块上。

    ``stack`` 跨页复用：章节标题只在出现的那一页写入，后续页的正文
    仍然继承该标题路径。
    """
    lines = text.split("\n")
    non_empty = [index for index, line in enumerate(lines) if line.strip()]
    edge_lines = set(non_empty[:2] + non_empty[-2:])
    blocks: list[TextBlock] = []
    buffer: list[str] = []

    def flush() -> None:
        content = normalize_text("\n".join(buffer))
        if content:
            heading_path = " > ".join(title for _, title in stack)
            blocks.append(
                TextBlock(text=content, page=page_number, heading_path=heading_path)
            )
        buffer.clear()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        # 页眉页脚纯页码：只过滤页面首尾两行，避免误删正文表格里的数字。
        if index in edge_lines and (
            _PAGE_NUMBER.match(stripped) or _PAGE_NUMBER_CN.match(stripped)
        ):
            continue
        heading = _heading_for(stripped, stack)
        if heading is not None:
            flush()
            level, title = heading
            stack[:] = [(lv, item) for lv, item in stack if lv < level]
            stack.append((level, title))
            continue
        buffer.append(stripped)

    flush()
    return blocks


def parse_pdf(data: bytes | Path) -> list[TextBlock]:
    try:
        reader = PdfReader(BytesIO(data) if isinstance(data, bytes) else data)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PDF 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001  单页提取失败不阻断其余页面
            continue
        text = normalize_text(text)
        if not text:
            continue
        blocks.extend(_blocks_from_page(text, page_number, heading_stack))

    if not blocks:
        raise ParseError("未从 PDF 中提取到文本，可能是扫描件或空文件")
    return blocks
