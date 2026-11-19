import hashlib
import re
from dataclasses import dataclass

from app.services.parsers.base import TextBlock

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;\n])")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+")


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


def _make_chunk(blocks: list[TextBlock], ordinal: int) -> ChunkData:
    text = "\n\n".join(block.text.strip() for block in blocks if block.text.strip()).strip()
    heading_path = next(
        (block.heading_path for block in blocks if block.heading_path), ""
    )
    pages = [block.page for block in blocks if block.page is not None]
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
) -> list[ChunkData]:
    """沿标题、段落和句子边界切片，保留来源元数据与少量重叠。"""
    expanded: list[TextBlock] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        for piece in _split_long_text(text, target_tokens):
            expanded.append(
                TextBlock(text=piece, page=block.page, heading_path=block.heading_path)
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
            if heading_changed and _buffer_tokens(buffer) >= min_tokens:
                chunks.append(_make_chunk(buffer, len(chunks)))
                buffer = []
            elif (
                buffer
                and _buffer_tokens(buffer) + estimate_tokens(block.text) > target_tokens
            ):
                chunks.append(_make_chunk(buffer, len(chunks)))
                last = buffer[-1]
                tail = _tail_text(last.text, overlap_tokens)
                buffer = (
                    [TextBlock(text=tail, page=last.page, heading_path=last.heading_path)]
                    if tail
                    else []
                )
        buffer.append(block)

    if buffer and (not chunks or _buffer_tokens(buffer) > overlap_tokens):
        chunks.append(_make_chunk(buffer, len(chunks)))

    return chunks
