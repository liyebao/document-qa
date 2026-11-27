"""按问题点名的结构编号补全原文。

问题常只给一个编号（「19条」「第3章」「第3.2节」），而检索是语义的：top_k
命中的往往只是编号附近的一段。另一份文件的同一条、或同一文件被分页切开的
下一段都不会进入上下文，模型只能答「无法确认」。

这里把「编号 → 原文」做成一条与编号形式无关的流程：
1. 抽取问题里的编号（条/章/节，中文数字与阿拉伯数字都支持）；
2. 判断证据里哪些「文件 + 编号」还没被覆盖；
3. 取回含该编号的原文作为种子；
4. 种子停在列举引导句上时，按窗口补齐后续片段。

新增编号形式（如页码、附录）只需要在 _PATTERNS 里加一条规则，
其余流程不必改动。
"""

import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document

# 一次最多补 6 处；同一文件最多 4 处（含承接分项列举的后续片段）。
MAX_REFERENCES = 3
MAX_FILL_CHUNKS = 10
MAX_FILL_CHARS = 8000
MAX_CONTINUATION_SPAN = 2

_DIGITS = "零一二三四五六七八九"
_CN_NUMERALS = "零〇一二三四五六七八九十百千两"
_NUMBER = rf"(?:[0-9]+(?:\.[0-9]+)*|[{_CN_NUMERALS}]{{1,6}})"

# 有「第」也不会被当成条号的情况：计数句（共七十九条）与相对指代（最后一条）。
_NOT_A_REFERENCE = rf"共计约超不足达有逾这那该本每下上前后此0-9{_CN_NUMERALS}"

_PATTERNS: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    # 第X条 / 第X章 / 第X节，X 可以是中文数字、阿拉伯数字或 3.2 这种节号。
    (re.compile(rf"第\s*({_NUMBER})\s*(条|章|节)"), "", True),
    # 省略「第」的条号：「71条第2项」「19条」。
    (re.compile(rf"(?<![{_NOT_A_REFERENCE}])({_NUMBER})\s*条"), "条", False),
    # 「§3.2」这类节号写法；单独的小数不认，避免把金额当编号。
    (re.compile(r"§\s*([0-9]+(?:\.[0-9]+)+)"), "节", False),
    # 「3.2节」。
    (
        re.compile(r"(?<![\d.])([0-9]+(?:\.[0-9]+)+)\s*节"),
        "节",
        False,
    ),
    # 中英文混用：article 33 / clause 33 / section 3.2。
    (
        re.compile(r"\b(?:article|art\.?|clause)\s*([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE),
        "条",
        False,
    ),
    (
        re.compile(r"\b(?:section|sec\.?)\s*([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE),
        "节",
        False,
    ),
)

# 以冒号收尾的片段，多半停在「履行下列职责：」这类列举引导句上。
# 只认这一种信号：页码页脚、脚注编号同样不以句号结尾，按「没有句号就算截断」
# 会把无关的下一段也补进来，白占预算。
_CONTINUATION_MARKS = ("：", ":")


@dataclass(frozen=True)
class Reference:
    """问题点名的结构编号。"""

    kind: str
    # 规范化后的写法，用于按「文件 + 编号」判断覆盖度。
    label: str
    # 原文里可能出现的写法，用于召回。
    variants: tuple[str, ...]

    def matches(self, text: str) -> bool:
        return any(re.search(_boundary(variant), text) for variant in self.variants)


def _to_chinese(value: int) -> str:
    if value < 10:
        return _DIGITS[value]
    if value < 20:
        return "十" + (_DIGITS[value % 10] if value % 10 else "")
    if value < 100:
        return _DIGITS[value // 10] + "十" + (_DIGITS[value % 10] if value % 10 else "")
    if value < 1000:
        rest = value % 100
        head = _DIGITS[value // 100] + "百"
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + _DIGITS[rest]
        return head + _to_chinese(rest)
    return str(value)


def _normalize_number(token: str) -> str:
    token = token.replace("两", "二").replace("〇", "零").strip()
    return _to_chinese(int(token)) if token.isdigit() else token


def normalize_number(token: str) -> str:
    """编号统一成中文写法；阿拉伯数字与中文数字都接受，供其它模块复用。"""
    return _normalize_number(token)


@lru_cache(maxsize=64)
def _boundary(variant: str) -> str:
    """编号在原文里的边界。

    「违反本条例第三十九条规定」只是引用，不是这一条本身；条号标题后面
    跟的通常是空格、冒号或另一份重复的标题，不会是连续汉字。节号则要
    避免 3.2 命中 3.25。
    """
    escaped = re.escape(variant)
    if variant and variant[0].isdigit():
        return rf"(?<![\d.]){escaped}(?![\d])"
    return rf"{escaped}(?![\u4e00-\u9fff0-9])"


def _reference(kind: str, number: str) -> Reference:
    normalized = _normalize_number(number)
    if normalized[0].isdigit():
        # 节号保持数字写法：原文标题是「3.2 预算风险」，不会写成「第三点二节」。
        return Reference(kind=kind, label=normalized, variants=(normalized,))
    label = f"第{normalized}{kind}"
    arabic = f"第{_to_arabic(normalized)}{kind}"
    variants = (label,) if arabic == label else (label, arabic)
    return Reference(kind=kind, label=label, variants=variants)


def _to_arabic(text: str) -> str:
    """中文数字还原成阿拉伯数字，用于同时匹配「第19条」这种写法。"""
    text = text.replace("两", "二").replace("〇", "零")
    digits = "零一二三四五六七八九"
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for char in text:
        if char in digits:
            current = digits.index(char)
        elif char in units:
            if current == 0 and char == "十":
                current = 1
            total += current * units[char]
            current = 0
        else:
            return text
    return str(total + current)


def extract_references(text: str, limit: int = MAX_REFERENCES) -> list[Reference]:
    """抽取问题里明确点名、又确实指向原文编号的条/章/节。"""
    question = text or ""
    hits: list[tuple[int, str, str]] = []
    for pattern, default_kind, has_kind_group in _PATTERNS:
        for match in pattern.finditer(question):
            # 「第X条」「第3.2节」已由第一条规则收走，省略式不要重复命中。
            if not has_kind_group and question[: match.start()].endswith("第"):
                continue
            kind = match.group(2) if has_kind_group else default_kind
            hits.append((match.start(), match.group(1), kind))

    found: list[Reference] = []
    seen: set[str] = set()
    for _, number, kind in sorted(hits):
        reference = _reference(kind, number)
        if reference.label in seen:
            continue
        seen.add(reference.label)
        found.append(reference)
        if len(found) >= limit:
            break
    return found


def references_in(text: str, references: list[Reference]) -> set[str]:
    """返回这段原文里以标题形式出现的编号。"""
    return {reference.label for reference in references if reference.matches(text or "")}


def needs_continuation(text: str) -> bool:
    """片段是否停在列举引导句的冒号上，需要接上分项内容。"""
    return (text or "").rstrip().endswith(_CONTINUATION_MARKS)


def _ready_chunks():
    """可用文件里的片段；权限与状态条件集中在这里，两个取数函数共用。"""
    return (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.status == DOCUMENT_STATUS_READY,
            Document.deleted_at.is_(None),
            Document.is_enabled.is_(True),
            Document.is_current.is_(True),
        )
    )


def fetch_reference_chunks(
    db: Session,
    *,
    collection_id: uuid.UUID,
    references: list[Reference],
    document_ids: list[uuid.UUID] | None = None,
    limit: int = MAX_FILL_CHUNKS,
) -> list[tuple[Chunk, Document]]:
    """取回含指定编号的原文，是否已覆盖由调用方按「文件 + 编号」判断。"""
    variants = [variant for reference in references for variant in reference.variants]
    if not variants:
        return []
    stmt = (
        _ready_chunks()
        .where(
            Collection.id == collection_id,
            or_(*(Chunk.text.like(f"%{variant}%") for variant in variants)),
        )
        .order_by(Chunk.document_id, Chunk.ordinal.asc())
        .limit(limit)
    )
    if document_ids is not None:
        stmt = stmt.where(Document.id.in_(document_ids))
    return list(db.execute(stmt).all())


def fetch_continuation_chunks(
    db: Session,
    *,
    collection_id: uuid.UUID,
    seeds: list[tuple[uuid.UUID, int]],
    span: int = 1,
) -> list[tuple[Chunk, Document]]:
    """取回种子片段之后的若干片段。

    条文常被分页切成「编号 + 引导句」和后面的分项列举两段，只补含编号的
    那一段会得到半句话。span 控制往后取几个片段，长表格/长列举可以调大。
    """
    span = max(1, min(span, MAX_CONTINUATION_SPAN))
    pairs = {
        (document_id, ordinal + offset)
        for document_id, ordinal in seeds
        for offset in range(1, span + 1)
    }
    if not pairs:
        return []
    stmt = (
        _ready_chunks()
        .where(
            Collection.id == collection_id,
            or_(
                *(
                    and_(Chunk.document_id == document_id, Chunk.ordinal == ordinal)
                    for document_id, ordinal in pairs
                )
            ),
        )
        .order_by(Chunk.document_id, Chunk.ordinal.asc())
    )
    return list(db.execute(stmt).all())
