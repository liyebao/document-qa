from app.models.chunk import Chunk


def source_location(chunk: Chunk) -> str:
    """把片段位置格式化成用户可读的页码和章节路径。

    有标题路径时只取最后一级（“第3章 > 3.2 预算风险” → “3.2 预算风险”），
    避免引用卡片被过长的层级撑开。
    """
    page = ""
    if chunk.page_start is not None:
        if chunk.page_end is not None and chunk.page_end != chunk.page_start:
            page = f"第 {chunk.page_start}–{chunk.page_end} 页"
        else:
            page = f"第 {chunk.page_start} 页"

    section = chunk.heading_path.split(" > ")[-1].strip() if chunk.heading_path else ""
    if section:
        section = section[:40]
    if page and section:
        return f"{page} · {section}"
    if page:
        return page
    if section:
        return section
    return "正文"
