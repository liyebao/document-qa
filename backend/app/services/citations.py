import re

UNCITED_WARNING = "\n\n（提示：本次回答未标注可核对的引用，请结合原文谨慎参考。）"


def validate_citations(answer: str, total: int) -> tuple[str, list[int]]:
    """只保留属于本轮候选的引用编号，非法编号直接剔除。"""
    used: list[int] = []

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 1 <= index <= total:
            if index not in used:
                used.append(index)
            return f"[{index}]"
        return ""

    cleaned = re.sub(r"\[(\d+)\]", replace, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, sorted(used)
