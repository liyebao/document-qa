"""跨格式共用的「编号型标题」识别规则。

PDF、DOC 这类格式拿不到字号和样式信息，只能靠「第X章、一、、（一）、1.2、
附录」这类编号判断层级；把规则抽成独立模块，多个解析器共用同一套判定，
避免不同格式对同一行文字给出不同的标题路径。
"""

from __future__ import annotations

import re

from app.services.parsers.base import TextBlock, normalize_text

# 只有编号足以说明层级；靠字号区分的版式不在正则里猜。
_CHAPTER = re.compile(r"^第\s*[〇零一二三四五六七八九十百千0-9]+\s*(章|节|篇|部分)\s*\S*")
_APPENDIX = re.compile(r"^附\s*录\s*[A-Za-z〇零一二三四五六七八九十0-9]*\s*\S*")
_CN_TOP = re.compile(r"^[一二三四五六七八九十]+\s*[、.．]\s*\S+")
_CN_SUB = re.compile(r"^[（(][一二三四五六七八九十]+[）)]\s*\S+")
# 每段编号最多两位：文档编号极少超过 99，而「2024.10.01」「2024 年」这类
# 正文日期一旦被当成标题，会把真正的章标题从标题栈里顶掉。
_NUM_MULTI = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\s*[、.．]?\s*(\S.*)$")
_NUM_SINGLE = re.compile(r"^(\d{1,3})\s*[、.．]\s*(\S.*)$")
_NUM_SPACE = re.compile(r"^(\d{1,2})\s+(\S.*)$")
# 编号后面跟这些词时几乎一定是正文里的数值（3.14 是圆周率 / 12.5% / 2024 年），
# 不是小节标题。
_NUM_TEXT_STOPWORDS = ("是", "为", "约", "等于", "占", "倍", "%", "％", "年", "月", "日", "元", "万", "亿")
_SENTENCE_MARKS = "。！？；"

MAX_HEADING_LENGTH = 60


def heading_for(line: str, stack: list[tuple[int, str]]) -> tuple[int, str] | None:
    """判断一行是否是标题，返回 (层级, 标题文本)。

    ``stack`` 是当前标题栈，用来处理“第一章”下面的“一、”“（一）”这类
    相对层级；层级只影响标题路径的裁剪，不影响正文。
    """
    text = line.strip()
    if not text or len(text) > MAX_HEADING_LENGTH:
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
        if multi.group(2).startswith(_NUM_TEXT_STOPWORDS):
            return None
        return min(multi.group(1).count(".") + 1, 4), text
    single = _NUM_SINGLE.match(text) or _NUM_SPACE.match(text)
    if single:
        title = single.group(2)
        if title.startswith(_NUM_TEXT_STOPWORDS):
            return None
        # 单级数字标题最容易和有序列表混淆：要求短、不带句读。
        if len(title) <= 30 and not any(mark in title for mark in "，,；;：:"):
            return 1, text
    return None


def push_heading(stack: list[tuple[int, str]], level: int, title: str) -> None:
    """把标题压入标题栈，并裁掉层级不低于它的旧标题。"""
    stack[:] = [(lv, item) for lv, item in stack if lv < level]
    stack.append((level, title))


def heading_path(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def paragraphs_to_blocks(
    paragraphs: list[str],
    *,
    heading_prefix: str = "",
    page: int | None = None,
    stack: list[tuple[int, str]] | None = None,
) -> list[TextBlock]:
    """把纯文本段落序列转成文本块。

    DOC 只有段落文本、没有样式表信息，用同一套编号规则推断标题；
    识别为标题的段落只进入标题路径，不再重复计入正文（与 PDF 一致，
    标题文本仍会通过 ``heading_path`` 进入检索用的 search_text）。

    传入 ``stack`` 可跨页复用标题栈，语义与 PDF 的 ``_blocks_from_page`` 一致。
    """
    if stack is None:
        stack = []
    prefix = [item for item in heading_prefix.split(" > ") if item]
    blocks: list[TextBlock] = []
    buffer: list[str] = []

    def flush() -> None:
        content = normalize_text("\n".join(buffer))
        buffer.clear()
        if not content:
            return
        parts = [*prefix, heading_path(stack)] if stack else prefix
        blocks.append(
            TextBlock(
                text=content,
                page=page,
                heading_path=" > ".join(part for part in parts if part),
            )
        )

    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text:
            flush()
            continue
        heading = heading_for(text, stack)
        if heading is not None:
            flush()
            push_heading(stack, *heading)
            continue
        buffer.append(text)

    flush()
    return blocks
