"""问题意图归一化：把同一意图的不同问法收敛到同一个规范化问题。

检索对措辞敏感——同一个问题换个说法，规划出的检索词和召回结果都会变。
这里不针对具体题目做匹配，而是抽取稳定的结构信息（意图类型、点名的
条/章/节、项号），据此生成标准问法，让同义问法走同一条检索路径。

意图指纹（kind + 编号 + 项号）同时是评测口径：同一意图的所有问法指纹
应当一致，指纹不一致就说明归一化漏了一种说法，不需要人工比对答案。
"""

import re
import unicodedata
from dataclasses import dataclass

from app.core.text_utils import normalize_query
from app.services.retrieval import reference_fill

KIND_COUNT = "count"
KIND_LAST = "last"
KIND_SCOPE = "scope"
KIND_CONTENT = "content"
KIND_UNKNOWN = "unknown"

# 同一意图在不同说法里的关键词；中英文混用也归到同一类。
_COUNT_MARKERS = (
    "多少条",
    "几条",
    "多少章",
    "几章",
    "条数",
    "总数",
    "总条数",
    "总共",
    "一共",
    "共计",
    "多少页",
    "how many",
    "total number",
)
_LAST_MARKERS = (
    "最后一条",
    "最后条文",
    "末尾一条",
    "末条",
    "last article",
    "last clause",
    "final article",
)
_SCOPE_MARKERS = (
    "有哪些",
    "列出",
    "全部",
    "目录",
    "清单",
    "list all",
    "all articles",
)

_ITEM_PATTERN = re.compile(r"第\s*([0-9]+|[一二三四五六七八九十]+)\s*[项款]")
# 口语说法：「第二个分项」「第 2 小项」。
_ITEM_COLLOQUIAL = re.compile(
    r"第\s*([0-9]+|[一二三四五六七八九十]+)\s*个?\s*(?:分项|小项)"
)
_PAREN_ITEM = re.compile(r"\(\s*([0-9]+|[一二三四五六七八九十]+)\s*\)")
_EN_ITEM = re.compile(r"\b(?:item|paragraph|para)\s*([0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class QuestionIntent:
    """一个问题的结构化意图；同义改写应当得到相同的 key。"""

    kind: str
    references: tuple[reference_fill.Reference, ...]
    items: tuple[str, ...]
    key: str
    variants: tuple[str, ...]


def normalize_text(question: str) -> str:
    """全角转半角、折叠空白，保证「７１条」「第 71 条」与「71条」等价。"""
    text = unicodedata.normalize("NFKC", question or "")
    return re.sub(r"\s+", " ", text).strip()


def _extract_items(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for pattern in (_ITEM_PATTERN, _ITEM_COLLOQUIAL, _PAREN_ITEM, _EN_ITEM):
        for match in pattern.finditer(text):
            tokens.append(match.group(1))
    items: list[str] = []
    for token in tokens:
        label = f"第{reference_fill.normalize_number(token)}项"
        if label not in items:
            items.append(label)
    return tuple(items)


def _classify(
    text: str,
    references: tuple[reference_fill.Reference, ...],
    items: tuple[str, ...],
) -> str:
    lowered = text.casefold()
    if any(marker in lowered for marker in _LAST_MARKERS):
        return KIND_LAST
    if any(marker in lowered for marker in _COUNT_MARKERS):
        return KIND_COUNT
    # 点名了具体编号时，问的就是这一条的内容，哪怕句子里出现「有哪些」。
    if references or items:
        return KIND_CONTENT
    if any(marker in lowered for marker in _SCOPE_MARKERS):
        return KIND_SCOPE
    return KIND_UNKNOWN


def _variants(
    kind: str,
    references: tuple[reference_fill.Reference, ...],
    items: tuple[str, ...],
) -> tuple[str, ...]:
    parts = [reference.label for reference in references] + list(items)
    if kind == KIND_CONTENT and len(references) > 1:
        # 多编号问题本身已带齐编号，再拼一条「三条编号 + 内容」只会稀释语义。
        return ()
    if kind == KIND_CONTENT and parts:
        primary = " ".join(parts) + " 内容 规定 原文"
        secondary = f"{references[0].label} 条文" if references else ""
    elif kind == KIND_COUNT:
        primary, secondary = "全文 一共 多少 条 条号 条文", ""
    elif kind == KIND_LAST:
        primary, secondary = "最后一条 条文 附则 施行", ""
    elif kind == KIND_SCOPE:
        primary, secondary = "全部 章节 目录 清单", ""
    else:
        primary, secondary = "", ""
    return tuple(variant for variant in (primary, secondary) if variant)


def understand(question: str) -> QuestionIntent:
    """把问题归一到「意图 + 编号 + 项号」，并给出标准检索问法。"""
    text = normalize_text(question)
    references = tuple(reference_fill.extract_references(text))
    items = _extract_items(text)
    kind = _classify(text, references, items)
    key_parts = [kind, *(reference.label for reference in references), *items]
    return QuestionIntent(
        kind=kind,
        references=references,
        items=items,
        key="|".join(key_parts),
        variants=_variants(kind, references, items),
    )


def expand_queries(question: str, limit: int = 1) -> list[str]:
    """原问题 + 至多 limit 条标准问法；用于同一子问题的补充检索。"""
    seen = {normalize_query(question)}
    expanded = [question]
    if limit <= 0:
        return expanded
    for variant in understand(question).variants:
        if normalize_query(variant) in seen:
            continue
        expanded.append(variant)
        seen.add(normalize_query(variant))
        if len(expanded) > limit:
            break
    return expanded


def alignment_hint(question: str) -> str:
    """把问题里的编号写法对齐到原文，给模型一条换算说明。

    这不是补充事实，只是编号体系的换算：问题里的「02条」即「第二条」，
    「第2项」与原文的「（二）」「第二项」「item 2」是同一项。
    """
    intent = understand(question)
    notes: list[str] = []
    if intent.references:
        labels = "、".join(f"「{reference.label}」" for reference in intent.references)
        notes.append(f"问题里的编号已规范为 {labels}（例如「02条」就是「第二条」）")
    if intent.items:
        labels = "、".join(intent.items)
        notes.append(
            f"问题中的 {labels} 是条内分项编号，原文可能写成「（二）」「第二项」"
            "或「item 2」，按序号一一对应"
        )
    if not notes:
        return ""
    return (
        "\n\n编号说明（用于对齐写法，不是资料内容）："
        + "；".join(notes)
        + "。不要因为写法不同就判定资料中没有该项。"
    )
