from io import BytesIO

from pptx import Presentation
from pptx.util import Inches

from app.services.chunking import chunk_blocks
from app.services.parsers.pptx import parse_pptx

FOOTER = "第 5 章 安全与权限 · Vastbase G100 V3.0.9"


def _add_lines(slide, lines: list[str], top: float = 1.0) -> None:
    box = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(8), Inches(4))
    frame = box.text_frame
    frame.text = lines[0]
    for line in lines[1:]:
        frame.add_paragraph().text = line


def _build_deck() -> bytes:
    presentation = Presentation()
    blank = presentation.slide_layouts[6]

    first = presentation.slides.add_slide(blank)
    _add_lines(first, ["5.1 用户管理", "①", "用户与角色不是一回事", "本机强制口令"])
    table = first.shapes.add_table(2, 2, Inches(0.5), Inches(3), Inches(6), Inches(1)).table
    table.cell(0, 0).text = "create user"
    table.cell(0, 1).text = "是（t）"
    table.cell(1, 0).text = "create role"
    table.cell(1, 1).text = "否（f）"
    _add_lines(first, [FOOTER, "06 / 42"], top=6.0)

    second = presentation.slides.add_slide(blank)
    _add_lines(second, ["5.1 用户管理", "②", "建用户顺带建了什么", "自动建同名 schema"])
    _add_lines(second, [FOOTER, "07 / 42"], top=6.0)

    buffer = BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_pptx_slide_title_becomes_heading_path() -> None:
    blocks = parse_pptx(_build_deck())

    assert [block.heading_path for block in blocks] == [
        "5.1 用户管理 > 用户与角色不是一回事",
        "5.1 用户管理 > 建用户顺带建了什么",
    ]


def test_pptx_drops_repeated_footer_and_page_numbers() -> None:
    blocks = parse_pptx(_build_deck())

    for block in blocks:
        assert FOOTER not in block.text
        assert "/ 42" not in block.text


def test_pptx_keeps_identical_table_cells() -> None:
    blocks = parse_pptx(_build_deck())

    assert "create user | 是（t）" in blocks[0].text
    assert "create role | 否（f）" in blocks[0].text


def test_pptx_chunks_follow_slides_when_heading_changes() -> None:
    blocks = parse_pptx(_build_deck())
    chunks = chunk_blocks(blocks, heading_split_tokens=0)

    assert len(chunks) == 2
    assert chunks[0].heading_path == "5.1 用户管理 > 用户与角色不是一回事"
    assert chunks[1].heading_path == "5.1 用户管理 > 建用户顺带建了什么"
    # 标题进 search_text，向量检索才能按小节召回。
    assert chunks[0].search_text.startswith("5.1 用户管理 > 用户与角色不是一回事\n")


def test_pptx_merges_slides_without_heading_split_setting() -> None:
    blocks = parse_pptx(_build_deck())
    chunks = chunk_blocks(blocks)

    assert len(chunks) == 1
