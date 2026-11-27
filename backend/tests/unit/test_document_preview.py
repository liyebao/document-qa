import uuid
from types import SimpleNamespace

from app.services.ingestion import _PREVIEW_MAX_BLOCKS, build_document_preview


class _FakeScalars:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _FakeDb:
    """只关心 scalars() 的返回，SQL 由真实查询负责，这里验证组装逻辑。"""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self, _stmt: object) -> _FakeScalars:
        return _FakeScalars(self._rows)


def _document() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), filename="报告.pdf", format="pdf")


def _chunk(ordinal: int, page: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        ordinal=ordinal,
        text=f"第{ordinal}段内容",
        page_start=page,
        page_end=page,
        heading_path="",
    )


def test_preview_returns_blocks_in_order() -> None:
    chunks = [_chunk(0, 1), _chunk(1, 2)]

    preview = build_document_preview(_FakeDb(chunks), _document())

    assert preview.truncated is False
    assert [block.ordinal for block in preview.blocks] == [0, 1]
    assert preview.blocks[0].text == "第0段内容"
    assert preview.blocks[1].source_location == "第 2 页"


def test_preview_truncates_long_documents() -> None:
    chunks = [_chunk(index, index + 1) for index in range(_PREVIEW_MAX_BLOCKS + 1)]

    preview = build_document_preview(_FakeDb(chunks), _document())

    assert preview.truncated is True
    assert len(preview.blocks) == _PREVIEW_MAX_BLOCKS


def test_preview_without_chunks_is_empty() -> None:
    preview = build_document_preview(_FakeDb([]), _document())

    assert preview.blocks == []
    assert preview.truncated is False
