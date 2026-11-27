"""回答生成后的质量自检。

只读检查回答正文与被引片段，发现问题就返回一段描述交给日志，不改写回答内容。
覆盖两类在真实问答里出现过的问题：

1. 片段里的相对指代（「见下一行说明」）被原样搬进独立的表格或段落——脱离原表之后，
   这句话既指不到东西，又会被当作结论读；
2. 代码块里的命令与原文不一致（改写参数、把「报错示例」当成「正确示例」）。
"""

from __future__ import annotations

import re

__all__ = [
    "check_answer",
    "dangling_references",
    "unsupported_code_lines",
]

_DANGLING_REFERENCE = re.compile(
    r"见(?:下一行|上一行|下一段|上一段|下文|上文|下表|上表|下图|上图)"
)
_FENCED_CODE = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)
_COMMENT_PREFIXES = ("--", "#", "//")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def dangling_references(answer: str) -> list[str]:
    """返回回答里出现的相对指代，去重后按字典序排列。"""
    return sorted({match.group(0) for match in _DANGLING_REFERENCE.finditer(answer)})


def unsupported_code_lines(answer: str, evidence_texts: list[str]) -> list[str]:
    """返回代码块里在证据片段中找不到原文的行（注释行不计）。"""
    haystack = "\n".join(_normalize(text) for text in evidence_texts)
    missing: list[str] = []
    for block in _FENCED_CODE.findall(answer):
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(_COMMENT_PREFIXES):
                continue
            if _normalize(stripped) not in haystack:
                missing.append(stripped)
    return missing


def check_answer(answer: str, evidence_texts: list[str]) -> list[str]:
    """把两类检查合成一份可读的警告列表；空列表表示没发现问题。"""
    warnings = [
        f"悬空指代：{reference}（原文的相对位置在答案里已经失效）"
        for reference in dangling_references(answer)
    ]
    warnings.extend(
        f"代码行不在被引片段里：{line[:80]}"
        for line in unsupported_code_lines(answer, evidence_texts)
    )
    return warnings
