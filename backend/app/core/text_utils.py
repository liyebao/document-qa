"""跨模块共享的文本处理：LIKE 转义、查询归一化与文件名清洗。"""

import re

UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def escape_like(term: str) -> str:
    """转义 LIKE 通配符，避免用户输入被当成模式匹配。"""
    # 反斜杠必须最先处理，否则后面补的转义符会被二次转义。
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_query(query: str) -> str:
    """查询去重口径：折叠空白并忽略大小写。"""
    return re.sub(r"\s+", " ", query).strip().lower()


def clean_filename_part(title: str, fallback: str, limit: int = 80) -> str:
    """清洗用作文件名的文本：替换非法字符、折叠空白并截断。"""
    cleaned = UNSAFE_FILENAME_CHARS.sub(" ", title or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:limit].strip()
    return cleaned or fallback
