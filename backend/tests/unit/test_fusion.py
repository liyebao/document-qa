import uuid

from app.services.retrieval.fusion import rrf_fuse

A = uuid.UUID("00000000-0000-0000-0000-000000000001")
B = uuid.UUID("00000000-0000-0000-0000-000000000002")
C = uuid.UUID("00000000-0000-0000-0000-000000000003")


def test_rrf_fuse_combines_ranked_lists() -> None:
    fused = rrf_fuse([[A, B], [B, C]], k=60)
    scores = dict(fused)

    assert scores[A] == 1 / 61
    assert scores[B] == 1 / 62 + 1 / 61
    assert scores[C] == 1 / 62
    assert fused[0][0] == B


def test_rrf_fuse_deduplicates_and_limits() -> None:
    fused = rrf_fuse([[A, A, B], [A, C]], k=60, top_k=2)
    assert len(fused) == 2
    assert fused[0][0] == A
    assert [chunk_id for chunk_id, _ in fused] == [A, C]


def test_rrf_fuse_empty_input() -> None:
    assert rrf_fuse([], k=60) == []
