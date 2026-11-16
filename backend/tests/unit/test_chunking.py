from app.services.chunking import chunk_blocks, estimate_tokens
from app.services.parsers.base import TextBlock


def test_estimate_tokens_counts_chinese_and_latin() -> None:
    assert estimate_tokens("项目风险") == 4
    assert estimate_tokens("RAG retrieval") == 2
    assert estimate_tokens("") == 0


def test_chunk_blocks_preserve_source_metadata() -> None:
    blocks = [
        TextBlock(text="第一段内容。" * 60, page=1, heading_path="第一章"),
        TextBlock(text="第二段内容。" * 60, page=2, heading_path="第一章"),
    ]
    chunks = chunk_blocks(blocks, target_tokens=120, min_tokens=60, overlap_tokens=10)

    assert len(chunks) >= 2
    assert chunks[0].page_start == 1
    assert all(chunk.heading_path == "第一章" for chunk in chunks)
    assert all(chunk.search_text.startswith("第一章") for chunk in chunks)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.fingerprint) == 64 for chunk in chunks)


def test_chunk_blocks_split_on_heading_change() -> None:
    blocks = [
        TextBlock(text="甲部分内容。" * 80, page=None, heading_path="甲"),
        TextBlock(text="乙部分内容。" * 80, page=None, heading_path="乙"),
    ]
    chunks = chunk_blocks(blocks, target_tokens=100, min_tokens=50, overlap_tokens=5)

    headings = {chunk.heading_path for chunk in chunks}
    assert "甲" in headings
    assert "乙" in headings


def test_chunk_blocks_ignore_empty_blocks() -> None:
    chunks = chunk_blocks(
        [TextBlock(text="   "), TextBlock(text="有效内容。" * 20)],
        target_tokens=100,
        min_tokens=50,
        overlap_tokens=5,
    )
    assert len(chunks) == 1
    assert "有效内容" in chunks[0].text
