from app.models.chunk import Chunk


def source_location(chunk: Chunk) -> str:
    """把片段位置格式化成用户可读的页码和章节路径。

    有标题路径时只取最后一级（“第3章 > 3.2 预算风险” → “3.2 预算风险”），
    避免引用卡片被过长的层级撑开。没有页码的资料（网页、表格）只显示章节。
    """
    return " · ".join(
        part for part in (_page_label(chunk), _section_label(chunk)) if part
    ) or "正文"


def _page_label(chunk: Chunk) -> str:
    start = chunk.page_start
    if start is None:
        return ""
    end = chunk.page_end
    if end is not None and end != start:
        return f"第 {start}–{end} 页"
    return f"第 {start} 页"


def _section_label(chunk: Chunk) -> str:
    if not chunk.heading_path:
        return ""
    return chunk.heading_path.split(" > ")[-1].strip()[:40]
