import uuid


def rrf_fuse(
    ranked_lists: list[list[uuid.UUID]],
    *,
    k: int = 60,
    top_k: int | None = None,
) -> list[tuple[uuid.UUID, float]]:
    """Reciprocal Rank Fusion：按名次融合多路召回，避免直接相加不同量纲的分数。"""
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    if top_k is not None:
        return ordered[:top_k]
    return ordered
