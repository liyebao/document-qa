from app.models.chunk import Chunk


def source_location(chunk: Chunk) -> str:
    """把片段位置格式化成用户可读的页码或章节路径。"""
    if chunk.page_start is not None:
        if chunk.page_end is not None and chunk.page_end != chunk.page_start:
            return f"第 {chunk.page_start}–{chunk.page_end} 页"
        return f"第 {chunk.page_start} 页"
    if chunk.heading_path:
        return chunk.heading_path
    return "正文"
