"""问法鲁棒性评测：同一意图换不同说法，系统是否仍给出稳定、完整的回答。

两种用法：

1. 只检查意图归一化（不调用模型，可放进 CI）：

    backend\\.venv\\Scripts\\python evaluation\\evaluate_paraphrases.py --offline

2. 真实接口评测（每个问法单独开一个会话，避免上下文影响）：

    backend\\.venv\\Scripts\\python evaluation\\evaluate_paraphrases.py ^
        --base-url http://127.0.0.1:8002 ^
        --collection-id <资料集 ID> ^
        --dataset evaluation\\paraphrase_cases.json

指标只报告本次实际运行的数据，不预设结论：
- 意图稳定性：所有问法是否归一到同一个意图指纹；
- 作答率：状态正常且没有落入「无法确认」；
- 要点命中率：回答里是否出现该意图的预期事实；
- 文件覆盖：预期文件是否都出现在引用里；
- 引用稳定性 / 回答稳定性：与第一个问法相比的 Jaccard 相似度。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import query_intent  # noqa: E402  需要 backend 在 sys.path 中

DEFAULT_BASE_URL = "http://localhost:8000"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
DEFAULT_DATASET = Path(__file__).resolve().parent / "paraphrase_cases.json"


def load_cases(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        try:
            cases = json.load(handle)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"数据集不是合法 JSON：{exc}") from exc
    if not isinstance(cases, list) or not cases:
        raise SystemExit("数据集为空或不是列表")
    for case in cases:
        missing = {"id", "expected_key", "paraphrases"} - set(case)
        if missing:
            raise SystemExit(f"用例 {case.get('id', '?')} 缺少字段：{sorted(missing)}")
    return cases


def intent_report(cases: list[dict]) -> dict:
    results = []
    stable = 0
    total = 0
    for case in cases:
        rows = []
        for question in case["paraphrases"]:
            key = query_intent.understand(question).key
            ok = key == case["expected_key"]
            rows.append({"question": question, "intent_key": key, "stable": ok})
            total += 1
            stable += int(ok)
        results.append(
            {
                "id": case["id"],
                "expected_key": case["expected_key"],
                "variants": rows,
            }
        )
    return {
        "intent_stability": round(stable / total, 3) if total else 0.0,
        "checked": total,
        "cases": results,
    }


def _signature(citations: list[dict]) -> set[str]:
    return {
        f"{citation.get('document_name', '')}@{citation.get('source_location', '')}"
        for citation in citations
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _bigrams(text: str) -> set[str]:
    compact = "".join(text.split())
    return {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}


def _answer_similarity(left: str, right: str) -> float:
    return _jaccard(_bigrams(left), _bigrams(right))


def ask(client: httpx.Client, collection_id: str, question: str) -> dict:
    conversation = client.post(f"/api/collections/{collection_id}/conversations", json={})
    conversation.raise_for_status()
    conversation_id = conversation.json()["id"]
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": question},
    )
    response.raise_for_status()
    assistant = response.json()["assistant_message"]
    return {
        "conversation_id": conversation_id,
        "question": question,
        "status": assistant["status"],
        "answer": assistant["content"],
        "citations": [
            {
                "document_name": citation["document_name"],
                "source_location": citation["source_location"],
            }
            for citation in assistant["citations"]
        ],
    }


def _is_insufficient(run: dict) -> bool:
    return "无法确认" in run["answer"][:80] or run["status"] != "completed"


def score_case(case: dict, runs: list[dict]) -> dict:
    base = runs[0]
    base_signature = _signature(base["citations"])
    points = case.get("expected_points", [])
    files = case.get("expected_files", [])
    answered = 0
    fact_hits = 0
    file_hits = 0
    citation_scores: list[float] = []
    answer_scores: list[float] = []
    for run in runs:
        answered += int(not _is_insufficient(run))
        fact_hits += int(all(point in run["answer"] for point in points))
        file_hits += int(
            all(
                any(expected in citation["document_name"] for citation in run["citations"])
                for expected in files
            )
        )
        citation_scores.append(_jaccard(base_signature, _signature(run["citations"])))
        answer_scores.append(_answer_similarity(base["answer"], run["answer"]))
    total = len(runs)
    return {
        "id": case["id"],
        "answered_rate": round(answered / total, 3),
        "fact_hit_rate": round(fact_hits / total, 3),
        "file_coverage_rate": round(file_hits / total, 3),
        "citation_stability": round(sum(citation_scores) / total, 3),
        "answer_stability": round(sum(answer_scores) / total, 3),
        "runs": runs,
    }


def summarize(case_scores: list[dict], intent: dict) -> dict:
    def mean(key: str) -> float:
        values = [case[key] for case in case_scores]
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "intent_stability": intent["intent_stability"],
        "answered_rate": mean("answered_rate"),
        "fact_hit_rate": mean("fact_hit_rate"),
        "file_coverage_rate": mean("file_coverage_rate"),
        "citation_stability": mean("citation_stability"),
        "answer_stability": mean("answer_stability"),
    }


def render_markdown(report: dict, dataset: Path) -> str:
    summary = report["summary"]
    lines = [
        "# 问法鲁棒性评测",
        "",
        f"- 数据集：`{dataset.name}`",
        f"- 运行时间：{report['created_at']}",
        f"- 模式：{'仅归一化检查' if report['offline'] else '真实接口'}",
        "",
        "## 汇总",
        "",
        "| 指标 | 数值 | 含义 |",
        "| --- | --- | --- |",
        f"| 意图稳定性 | {summary['intent_stability']:.3f} | 所有问法归一到同一意图指纹的比例 |",
        f"| 作答率 | {summary['answered_rate']:.3f} | 未落入「无法确认」的比例 |",
        f"| 要点命中率 | {summary['fact_hit_rate']:.3f} | 回答包含预期事实的比例 |",
        f"| 文件覆盖 | {summary['file_coverage_rate']:.3f} | 预期文件都出现在引用里的比例 |",
        f"| 引用稳定性 | {summary['citation_stability']:.3f} | 与首个问法的引用 Jaccard 均值 |",
        f"| 回答稳定性 | {summary['answer_stability']:.3f} | 与首个问法的回答二元组 Jaccard 均值 |",
        "",
    ]
    if not report["offline"]:
        lines += [
            "## 用例",
            "",
            "| 用例 | 作答率 | 要点命中 | 文件覆盖 | 引用稳定 | 回答稳定 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for case in report["cases"]:
            lines.append(
                f"| {case['id']} | {case['answered_rate']:.3f} | {case['fact_hit_rate']:.3f} "
                f"| {case['file_coverage_rate']:.3f} | {case['citation_stability']:.3f} "
                f"| {case['answer_stability']:.3f} |"
            )
        lines.append("")
    lines += ["## 意图归一化", ""]
    for case in report["intent"]["cases"]:
        lines.append(f"### {case['id']}（期望 `{case['expected_key']}`）")
        lines.append("")
        for variant in case["variants"]:
            flag = "通过" if variant["stable"] else "不一致"
            lines.append(f"- {flag}：`{variant['question']}` → `{variant['intent_key']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--collection-id", default="")
    parser.add_argument("--offline", action="store_true", help="只检查意图归一化，不调用模型")
    parser.add_argument(
        "--case", action="append", default=[], help="只跑指定用例 id，可重复传入"
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]
        if not cases:
            raise SystemExit(f"没有匹配的用例：{sorted(wanted)}")
    intent = intent_report(cases)
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "offline": args.offline,
        "dataset": str(args.dataset),
        "intent": intent,
        "cases": [],
        "summary": {},
    }

    if not args.offline:
        if not args.collection_id:
            raise SystemExit("真实接口评测需要 --collection-id；只想检查归一化请加 --offline")
        with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
            for case in cases:
                runs = [ask(client, args.collection_id, q) for q in case["paraphrases"]]
                report["cases"].append(score_case(case, runs))
        report["summary"] = summarize(report["cases"], intent)
    else:
        report["summary"] = {
            "intent_stability": intent["intent_stability"],
            "answered_rate": 0.0,
            "fact_hit_rate": 0.0,
            "file_coverage_rate": 0.0,
            "citation_stability": 0.0,
            "answer_stability": 0.0,
        }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORTS_DIR / f"{stamp}-paraphrase.json"
    md_path = REPORTS_DIR / f"{stamp}-paraphrase.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report, args.dataset), encoding="utf-8")

    summary = report["summary"]
    print(f"意图稳定性 {summary['intent_stability']:.3f}")
    if not args.offline:
        print(f"作答率 {summary['answered_rate']:.3f}｜要点命中 {summary['fact_hit_rate']:.3f}")
        print(f"引用稳定性 {summary['citation_stability']:.3f}｜回答稳定性 {summary['answer_stability']:.3f}")
    print(f"报告：{json_path}\n      {md_path}")


if __name__ == "__main__":
    main()
