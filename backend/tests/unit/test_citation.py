from app.services.answering import validate_citations


def test_validate_citations_keeps_valid_indices() -> None:
    cleaned, used = validate_citations("结论一[1]，结论二[2]，再次引用[1]。", total=2)
    assert used == [1, 2]
    assert "[1]" in cleaned
    assert "[2]" in cleaned


def test_validate_citations_removes_out_of_range_indices() -> None:
    cleaned, used = validate_citations("有依据的结论[1]，编造的来源[5]。", total=2)
    assert used == [1]
    assert "[5]" not in cleaned
    assert "编造的来源" in cleaned


def test_validate_citations_without_markers() -> None:
    cleaned, used = validate_citations("当前资料无法确认。", total=3)
    assert cleaned == "当前资料无法确认。"
    assert used == []
