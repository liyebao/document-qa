from app.services.chunking import chunk_blocks
from app.services.parsers.base import TextBlock
from app.services.parsers.tables import blocks_from_rows


def _table(rows: int) -> str:
    lines = ["| 型号 | 转速 | 备注 |", "| --- | --- | --- |"]
    lines.extend(f"| DMC-{index} | {index * 100} | 说明{index} |" for index in range(rows))
    return "\n".join(lines)


def test_table_splits_on_row_boundaries_and_repeats_header():
    text = _table(80)

    chunks = chunk_blocks(
        [TextBlock(text=text, kind="table")],
        target_tokens=120,
        min_tokens=60,
        overlap_tokens=10,
    )

    assert len(chunks) > 1
    body_rows: list[str] = []
    for chunk in chunks:
        lines = chunk.text.splitlines()
        # 每片都带表头，行不会被劈成两半。
        assert lines[0] == "| 型号 | 转速 | 备注 |"
        assert set(lines[1].replace(" ", "")) <= {"|", "-"}
        body_rows.extend(line for line in lines[2:] if line.strip())
    assert body_rows == [
        f"| DMC-{index} | {index * 100} | 说明{index} |" for index in range(80)
    ]


def test_untyped_markdown_table_is_detected_and_kept_whole_rows():
    # 解析器没标 kind 时，按 Markdown 形状兜底识别。
    chunks = chunk_blocks(
        [TextBlock(text=_table(30))],
        target_tokens=80,
        min_tokens=40,
        overlap_tokens=10,
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.text.splitlines()[0] == "| 型号 | 转速 | 备注 |"
        assert all("DMC-" in line for line in chunk.text.splitlines()[2:] if line.strip())


def test_table_blocks_from_rows_are_marked_as_table():
    blocks = blocks_from_rows([["型号", "转速"], ["DMC-1", "100"]])

    assert blocks and all(block.kind == "table" for block in blocks)


def test_search_text_carries_document_breadcrumb():
    blocks = [
        TextBlock(
            text="5.1 用户管理\n用户与角色不是一回事。",
            page=5,
            heading_path="5.1 用户管理 > 用户与角色不是一回事",
        )
    ]

    chunks = chunk_blocks(blocks, document_title="第05章-安全与权限.pptx")

    assert chunks[0].search_text.startswith(
        "【文档】第05章-安全与权限.pptx｜【章节】5.1 用户管理 > 用户与角色不是一回事｜【位置】第 5 页\n"
    )
    # 原文保持干净：引用快照与答案都不该看到面包屑。
    assert chunks[0].text.startswith("5.1 用户管理")


def test_search_text_without_document_title_keeps_old_shape():
    blocks = [TextBlock(text="第一章 概述\n正文。", heading_path="第一章 概述")]

    chunks = chunk_blocks(blocks)

    assert chunks[0].search_text == "第一章 概述\n第一章 概述\n正文。"
