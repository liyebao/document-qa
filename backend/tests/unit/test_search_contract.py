import pytest
from pydantic import ValidationError

from app.schemas.conversation import ConversationTitleUpdate
from app.services.search import escape_like


def test_escape_like_escapes_backslash_percent_and_underscore() -> None:
    # 反斜杠先转义，再转义 % 与 _；结果交给 ilike(..., escape="\\") 使用。
    assert escape_like("100%_done") == "100\\%\\_done"
    assert escape_like("a\\b") == "a\\\\b"
    assert escape_like("50%_\\") == "50\\%\\_\\\\"


def test_escape_like_keeps_plain_cjk_text() -> None:
    assert escape_like("七步") == "七步"


@pytest.mark.parametrize("value", ["", "   ", "\t\n "])
def test_title_update_rejects_blank_after_strip(value: str) -> None:
    with pytest.raises(ValidationError):
        ConversationTitleUpdate(title=value)


def test_title_update_strips_and_accepts_boundary_lengths() -> None:
    assert ConversationTitleUpdate(title="  七步  ").title == "七步"
    longest = "a" * 200
    assert ConversationTitleUpdate(title=longest).title == longest
    # 前后空白不计入 200 字符上限。
    assert ConversationTitleUpdate(title=f"  {longest}  ").title == longest


def test_title_update_rejects_over_200_after_strip() -> None:
    with pytest.raises(ValidationError):
        ConversationTitleUpdate(title="a" * 201)
