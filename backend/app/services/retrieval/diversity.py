"""MMR 多样性重排：避免同一文件的相邻片段占满上下文。

RRF 只按名次融合，跨文件比较类问题容易让同一份文档的连续切片占满 top_k，
导致另一份对比材料根本没有机会进入上下文。这里用 MMR（Maximal Marginal
Relevance）在相关性与冗余度之间折中，并对单文件条数设软上限，余量再按分数回补，
保证不会因为多样性约束而让上下文变短。
"""

import uuid

DEFAULT_MMR_LAMBDA = 0.7
DEFAULT_MAX_PER_DOCUMENT = 2


def _unit_vector(values: object) -> list[float] | None:
    """归一化向量；pgvector 返回 numpy 数组，统一转成 list 便于后续点积。"""
    if values is None:
        return None
    try:
        items = [float(value) for value in values]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    norm = sum(value * value for value in items) ** 0.5
    if not items or norm <= 0:
        return None
    return [value / norm for value in items]


def _dot(left: list[float] | None, right: list[float] | None) -> float:
    if left is None or right is None or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def mmr_select(
    candidates: list[tuple[uuid.UUID, float]],
    *,
    vectors: dict[uuid.UUID, list[float] | None],
    document_ids: dict[uuid.UUID, uuid.UUID],
    limit: int,
    lambda_: float = DEFAULT_MMR_LAMBDA,
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT,
) -> list[tuple[uuid.UUID, float]]:
    """按 MMR 选出 limit 条候选，顺序即最终上下文顺序。

    candidates 需按相关性降序排列，score 会被归一化后作为相关性分量；
    vectors 缺失时退化为纯相关性排序（仍保留单文件软上限）。
    """
    if limit <= 0 or not candidates:
        return []

    max_score = max((score for _, score in candidates if score > 0), default=0.0)
    relevance = {
        chunk_id: (score / max_score if max_score > 0 else 0.0)
        for chunk_id, score in candidates
    }
    prepared = {chunk_id: _unit_vector(vectors.get(chunk_id)) for chunk_id, _ in candidates}

    selected: list[tuple[uuid.UUID, float]] = []
    selected_ids: set[uuid.UUID] = set()
    per_document: dict[uuid.UUID, int] = {}
    remaining = list(candidates)

    while remaining and len(selected) < limit:
        best_index = -1
        best_value = float("-inf")
        for index, (chunk_id, _) in enumerate(remaining):
            document_id = document_ids.get(chunk_id)
            if (
                max_per_document > 0
                and document_id is not None
                and per_document.get(document_id, 0) >= max_per_document
            ):
                continue
            redundancy = 0.0
            for picked_id in selected_ids:
                similarity = _dot(prepared.get(chunk_id), prepared.get(picked_id))
                if similarity > redundancy:
                    redundancy = similarity
            value = lambda_ * relevance.get(chunk_id, 0.0) - (1 - lambda_) * redundancy
            if value > best_value:
                best_value = value
                best_index = index
        if best_index < 0:
            break

        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_ids.add(chosen[0])
        document_id = document_ids.get(chosen[0])
        if document_id is not None:
            per_document[document_id] = per_document.get(document_id, 0) + 1

    # 软上限：候选文件不足时按原分数顺序回补，不让上下文变短。
    if len(selected) < limit:
        for item in candidates:
            if len(selected) >= limit:
                break
            if item[0] in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item[0])

    return selected[:limit]
