import hashlib
import re
from dataclasses import dataclass

from app.services.parsers.base import TextBlock

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;\n])")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+")
_TABLE_LINE = re.compile(r"^\|.*\|$")
_TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")


@dataclass(frozen=True)
class ChunkData:
    text: str
    search_text: str
    heading_path: str
    page_start: int | None
    page_end: int | None
    ordinal: int
    fingerprint: str


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文按字计，英文按词计，标点按半个计。"""
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN_WORD.findall(text))
    punctuation = len(re.findall(r"[，。；：！？、,.;:!?]", text))
    return cjk + latin + punctuation // 2


def _slice_by_token_budget(text: str, target_tokens: int) -> list[str]:
    """按估算 token 数切片，而不是把 target_tokens 直接当字符数用。

    中英文混排时字符数与 token 数比例不同；用当前文本的比例换算切分步长，
    避免英文长句被切得比目标短 5–6 倍。
    """
    total = estimate_tokens(text)
    if total <= target_tokens:
        return [text]
    step = max(1, int(len(text) * target_tokens / max(total, 1)))
    pieces = []
    for index in range(0, len(text), step):
        piece = text[index : index + step].strip()
        if piece:
            pieces.append(piece)
    return pieces


def _is_table_text(text: str) -> bool:
    """判断一段文本是不是 Markdown 表格（解析器没标 kind 时的兜底）。"""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    if not all(_TABLE_LINE.match(line) for line in lines):
        return False
    return any(_TABLE_SEPARATOR.match(line) for line in lines[:2])


def _split_table_text(text: str, target_tokens: int) -> list[str]:
    """按行切表格，并把表头复制进每一片。

    表格一旦按句子/字符切，行会被劈成两半、表头只留在第一片，模型拿到
    ``| DMC-1000 | 24000 | 20 | 40 |`` 这种没有列名的碎片就只能瞎猜。
    所以这里只允许在行边界切开，且每片都重新带上表头与分隔行。
    """

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or not _TABLE_SEPARATOR.match(lines[1].strip()):
        return _split_long_text(text, target_tokens)

    header, separator, body = lines[0], lines[1], lines[2:]
    header_tokens = estimate_tokens(header) + estimate_tokens(separator)

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = header_tokens
    for row in body:
        row_tokens = estimate_tokens(row)
        if current and current_tokens + row_tokens > target_tokens:
            pieces.append("\n".join([header, separator, *current]))
            current = []
            current_tokens = header_tokens
        current.append(row)
        current_tokens += row_tokens
    if current:
        pieces.append("\n".join([header, separator, *current]))
    return pieces or [text]


def _split_long_text(text: str, target_tokens: int) -> list[str]:
    if estimate_tokens(text) <= target_tokens:
        return [text]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_BOUNDARY.split(text):
        if not sentence:
            continue
        if estimate_tokens(current) + estimate_tokens(sentence) > target_tokens and current:
            pieces.append(current.strip())
            current = ""
        if estimate_tokens(sentence) > target_tokens:
            pieces.extend(_slice_by_token_budget(sentence, target_tokens))
            continue
        current += sentence
    if current.strip():
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def _tail_text(text: str, max_tokens: int) -> str:
    tail: list[str] = []
    total = 0
    for sentence in reversed([item for item in _SENTENCE_BOUNDARY.split(text) if item.strip()]):
        tokens = estimate_tokens(sentence)
        if total + tokens > max_tokens:
            break
        tail.insert(0, sentence)
        total += tokens
    return "".join(tail).strip()


def _buffer_tokens(blocks: list[TextBlock]) -> int:
    return sum(estimate_tokens(block.text) for block in blocks)


def _breadcrumb(
    document_title: str, heading_path: str, pages: list[int]
) -> str:
    """检索用的元数据面包屑：文档 → 章节 → 页码。

    只把正文送进向量时，「违约金按 0.5%/日 计算」这种句子离开原文就失去
    归属；带上文档名与完整章节路径后，向量能聚到同一主题，BM25 也能靠
    「第 05 章」「安全与权限」这些头部词命中。
    """

    parts: list[str] = []
    if document_title:
        parts.append(f"【文档】{document_title}")
    if heading_path:
        parts.append(f"【章节】{heading_path}")
    if pages:
        parts.append(f"【位置】第 {pages[0]} 页")
    return "｜".join(parts)


def _make_chunk(
    blocks: list[TextBlock], ordinal: int, *, document_title: str = ""
) -> ChunkData:
    text = "\n\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()
    heading_path = next(
        (block.heading_path for block in blocks if block.heading_path), ""
    )
    pages = [block.page for block in blocks if block.page is not None]
    if document_title:
        breadcrumb = _breadcrumb(
            document_title,
            heading_path,
            [min(pages)] if pages else [],
        )
        # search_text 只用于检索；text 保持原文，引用快照与答案都以它为准。
        search_text = f"{breadcrumb}\n{text}" if breadcrumb else text
    else:
        search_text = f"{heading_path}\n{text}".strip() if heading_path else text
    return ChunkData(
        text=text,
        search_text=search_text,
        heading_path=heading_path,
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        ordinal=ordinal,
        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def chunk_blocks(
    blocks: list[TextBlock],
    *,
    target_tokens: int = 800,
    min_tokens: int = 600,
    overlap_tokens: int = 80,
    heading_split_tokens: int | None = None,
    document_title: str = "",
) -> list[ChunkData]:
    """沿标题、段落和句子边界切片，保留来源元数据与少量重叠。

    ``heading_split_tokens`` 用于按页组织的文档（如幻灯片）：只要标题变了就切
    新块，不必等缓冲区攒到 ``min_tokens``，避免一页一个知识点被拼进同一块。
    ``document_title`` 会写进每块的检索面包屑（文档名 + 章节路径 + 页码），
    让脱离原文的片段仍然带着归属。
    """
    heading_threshold = min_tokens if heading_split_tokens is None else heading_split_tokens
    expanded: list[TextBlock] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        is_table = block.kind == "table" or _is_table_text(text)
        pieces = (
            _split_table_text(text, target_tokens)
            if is_table
            else _split_long_text(text, target_tokens)
        )
        for piece in pieces:
            expanded.append(
                TextBlock(
                    text=piece,
                    page=block.page,
                    heading_path=block.heading_path,
                    kind="table" if is_table else block.kind,
                )
            )

    chunks: list[ChunkData] = []
    buffer: list[TextBlock] = []

    for block in expanded:
        if buffer:
            heading_changed = (
                block.heading_path
                and buffer[-1].heading_path
                and block.heading_path != buffer[-1].heading_path
            )
            if heading_changed and _buffer_tokens(buffer) >= heading_threshold:
                chunks.append(_make_chunk(buffer, len(chunks), document_title=document_title))
                buffer = []
            elif (
                buffer
                and _buffer_tokens(buffer) + estimate_tokens(block.text) > target_tokens
            ):
                chunks.append(_make_chunk(buffer, len(chunks), document_title=document_title))
                last = buffer[-1]
                # 表格重叠不能只截尾巴：少了表头的几行数据比没有更误导。
                tail = "" if last.kind == "table" else _tail_text(last.text, overlap_tokens)
                buffer = (
                    [TextBlock(text=tail, page=last.page, heading_path=last.heading_path)]
                    if tail
                    else []
                )
        buffer.append(block)

    if buffer and any(block.text.strip() for block in buffer):
        chunks.append(_make_chunk(buffer, len(chunks), document_title=document_title))

    return chunks
