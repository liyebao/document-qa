"""离线评测指标：只对实际运行记录做统计，不预设目标值。"""

import math


def refusal_accuracy(records: list[dict]) -> float | None:
    """拒答准确性：无答案题是否拒答，有答案题是否没有误拒答。"""
    if not records:
        return None
    correct = 0
    for record in records:
        refused = "当前资料无法确认" in record.get("answer", "")
        if refused == bool(record.get("expected_refusal")):
            correct += 1
    return correct / len(records)


def citation_presence_rate(records: list[dict]) -> float | None:
    """有答案问题中，至少给出一条引用的比例。"""
    answerable = [record for record in records if not record.get("expected_refusal")]
    if not answerable:
        return None
    with_citation = sum(1 for record in answerable if record.get("citations"))
    return with_citation / len(answerable)


def answer_point_recall(records: list[dict]) -> float | None:
    """预期答案要点的字符串命中率；只作为人工核对前的粗略指标。"""
    scored = [record for record in records if record.get("expected_points")]
    if not scored:
        return None
    total = 0
    hit = 0
    for record in scored:
        answer = record.get("answer", "")
        for point in record["expected_points"]:
            total += 1
            if point and point in answer:
                hit += 1
    return hit / total if total else None


def _normalize(value: object) -> str:
    return str(value).strip().casefold()


def first_relevant_rank(ranked: list[object], gold: list[object]) -> int | None:
    """返回第一个命中项的 1-based 排名，未命中返回 None。"""
    gold_set = {_normalize(item) for item in gold if str(item).strip()}
    if not gold_set:
        return None
    for index, item in enumerate(ranked, start=1):
        if _normalize(item) in gold_set:
            return index
    return None


def recall_at_k(ranked: list[object], gold: list[object], k: int) -> float | None:
    """单题 Recall@K：命中任一标注项记 1，否则记 0。"""
    if not gold:
        return None
    rank = first_relevant_rank(ranked[:k], gold)
    return 1.0 if rank is not None else 0.0


def reciprocal_rank(ranked: list[object], gold: list[object]) -> float | None:
    if not gold:
        return None
    rank = first_relevant_rank(ranked, gold)
    return 1.0 / rank if rank is not None else 0.0


def ndcg_at_k(ranked: list[object], gold: list[object], k: int) -> float | None:
    """二值标注下的 nDCG@K：奖励命中项排在更靠前的位置。

    与 recall_at_k 的"命中任一记 1"不同，这里区分第 1 名和第 5 名，
    适合比较不同重排策略的排序质量。没有标注时返回 None。
    """
    gold_set = {_normalize(item) for item in gold if str(item).strip()}
    if not gold_set or k <= 0:
        return None
    dcg = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        if _normalize(item) in gold_set:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(k, len(gold_set))
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    if ideal <= 0:
        return None
    return dcg / ideal


def _retrieval_values(record: dict, level: str) -> tuple[list, list]:
    if level == "chunks":
        ranked = record.get("retrieved_chunk_ids") or []
        gold = record.get("expected_chunk_ids") or []
    else:
        ranked = record.get("retrieved_documents") or []
        gold = record.get("expected_files") or []
    return list(ranked), list(gold)


def retrieval_recall_at_k(
    records: list[dict], k: int, level: str = "documents"
) -> float | None:
    """按文件或片段计算的 Recall@K；没有标注时返回 None。"""
    values = [
        recall_at_k(*_retrieval_values(record, level), k=k)
        for record in records
        if _retrieval_values(record, level)[1]
    ]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def retrieval_mrr(records: list[dict], level: str = "documents") -> float | None:
    values = [
        reciprocal_rank(*_retrieval_values(record, level))
        for record in records
        if _retrieval_values(record, level)[1]
    ]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def retrieval_ndcg_at_k(
    records: list[dict], k: int, level: str = "documents"
) -> float | None:
    """按文件或片段计算的 nDCG@K；没有标注时返回 None。"""
    values = [
        ndcg_at_k(*_retrieval_values(record, level), k=k)
        for record in records
        if _retrieval_values(record, level)[1]
    ]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def summarize(records: list[dict]) -> dict[str, float | int | None]:
    return {
        "total": len(records),
        "refusal_accuracy": refusal_accuracy(records),
        "citation_presence_rate": citation_presence_rate(records),
        "answer_point_recall": answer_point_recall(records),
        "retrieval_recall_at_5": retrieval_recall_at_k(records, 5),
        "retrieval_recall_at_10": retrieval_recall_at_k(records, 10),
        "retrieval_mrr": retrieval_mrr(records),
        "retrieval_ndcg_at_10": retrieval_ndcg_at_k(records, 10),
        "chunk_recall_at_5": retrieval_recall_at_k(records, 5, level="chunks"),
        "chunk_mrr": retrieval_mrr(records, level="chunks"),
        "chunk_ndcg_at_10": retrieval_ndcg_at_k(records, 10, level="chunks"),
    }
