from types import SimpleNamespace

from app.services.locations import source_location


def _chunk(
    page_start: int | None = 3,
    page_end: int | None = None,
    heading_path: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        page_start=page_start, page_end=page_end, heading_path=heading_path
    )


def test_location_combines_page_and_last_heading() -> None:
    chunk = _chunk(heading_path="第一章 风险 > 3.2 预算风险")
    assert source_location(chunk) == "第 3 页 · 3.2 预算风险"


def test_location_keeps_page_range() -> None:
    chunk = _chunk(page_start=3, page_end=5, heading_path="3.2 预算风险")
    assert source_location(chunk) == "第 3–5 页 · 3.2 预算风险"


def test_location_falls_back_to_heading_or_text() -> None:
    assert source_location(_chunk(page_start=None, heading_path="甲 > 乙")) == "乙"
    assert source_location(_chunk(page_start=None)) == "正文"
