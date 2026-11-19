from app.services.parsers.pdf import _blocks_from_page, _heading_for


def test_heading_levels_follow_numbering_style() -> None:
    assert _heading_for("第一章 项目背景", []) == (1, "第一章 项目背景")
    assert _heading_for("第2节 适用范围", []) == (2, "第2节 适用范围")
    assert _heading_for("3.2 预算风险", []) == (2, "3.2 预算风险")
    assert _heading_for("3.2.1 预算上限", []) == (3, "3.2.1 预算上限")
    assert _heading_for("附录 A 术语表", []) == (1, "附录 A 术语表")


def test_relative_heading_levels_use_current_stack() -> None:
    chapter = [(1, "第一章 项目背景")]
    assert _heading_for("一、总体要求", chapter) == (2, "一、总体要求")

    nested = [(1, "第一章 项目背景"), (2, "一、总体要求")]
    assert _heading_for("（一）适用范围", nested) == (3, "（一）适用范围")


def test_sentences_and_numbered_lists_are_not_headings() -> None:
    assert _heading_for("如延期超过两周，应追加 15% 预算。", []) is None
    assert _heading_for("1. 首先，我们需要梳理风险来源。", []) is None
    assert _heading_for("2024 年项目按计划推进。", []) is None


def test_blocks_carry_heading_path_and_skip_page_numbers() -> None:
    stack: list[tuple[int, str]] = []
    text = "\n".join(
        [
            "1",
            "第一章 项目背景",
            "项目概况。",
            "",
            "3.2 预算风险",
            "如延期超过两周，应追加 15% 预算。",
            "- 2 -",
        ]
    )

    blocks = _blocks_from_page(text, page_number=3, stack=stack)

    assert [block.heading_path for block in blocks] == [
        "第一章 项目背景",
        "第一章 项目背景 > 3.2 预算风险",
    ]
    assert [block.page for block in blocks] == [3, 3]
    # 页首/页尾的纯页码不进入正文。
    assert "1\n" not in blocks[0].text
    assert "- 2 -" not in blocks[1].text


def test_heading_stack_survives_page_break() -> None:
    stack: list[tuple[int, str]] = []
    first = _blocks_from_page("第二章 预算管理\n正文一。", 1, stack)
    second = _blocks_from_page("正文二。", 2, stack)

    assert first[0].heading_path == "第二章 预算管理"
    assert second[0].heading_path == "第二章 预算管理"
    assert second[0].page == 2


def test_heading_only_page_produces_no_empty_block() -> None:
    stack: list[tuple[int, str]] = []
    blocks = _blocks_from_page("第一章 项目背景", 1, stack)

    assert blocks == []
    assert stack == [(1, "第一章 项目背景")]


def test_pdf_without_headings_keeps_empty_path() -> None:
    blocks = _blocks_from_page("第一段。\n\n第二段。", 1, [])

    assert [block.heading_path for block in blocks] == ["", ""]
    assert [block.text for block in blocks] == ["第一段。", "第二段。"]
