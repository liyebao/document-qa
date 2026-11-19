"""检索分词：入库与查询必须使用同一套规则，否则词频与文档频率会对不上。"""

import re

import jieba

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN_TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")

_STOPWORDS = frozenset(
    """
    的 了 和 是 在 有 与 及 或 就 都 而 也 这 那 其 为 对 从 到 由 以 于 被 把 让 给
    一个 一些 我们 你们 他们 它们 以及 但是 因为 所以 如果 虽然 然后 并且 或者 而且
    可以 需要 进行 通过 关于 对于 根据 按照 由于 因此 其中 其他 相关 一下 这个 那个
    这些 那些 上述 什么 哪些 哪个 怎么 如何 是否 多少 请问 请问 以便 用于 属于
    the a an and or of to in for on with is are was were be been being it this that
    these those as at by from into over under about than then there their its
    """.split()
)


def tokenize(text: str) -> list[str]:
    """使用 jieba 搜索模式切词，过滤单字、停用词与纯标点。"""
    if not text:
        return []
    tokens: list[str] = []
    for raw in jieba.cut_for_search(text):
        term = raw.strip().lower()
        # 单字通常噪声太大，但“第5章”里的 5 是精确匹配的关键，单独保留数字。
        if (len(term) < 2 and not term.isdigit()) or term in _STOPWORDS:
            continue
        if not (_CJK.search(term) or _LATIN_TERM.fullmatch(term)):
            continue
        tokens.append(term)
    return tokens
