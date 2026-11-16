"""从后端 retrieval_trace 日志计算文件级/片段级 Recall@K 与 MRR。

用法：
    backend\\.venv\\Scripts\\python evaluation\\analyze_traces.py ^
        --log logs\\backend.log ^
        --report evaluation\\reports\\<运行报告>.json

日志中的检索轨迹包含检索查询词、chunk_id、document_id、文件名和 RRF 分数，
不包含资料正文与 API Key。脚本把报告里的 `expected_files`
与 `expected_chunk_ids` 和轨迹中的 fused 排名对比，输出聚合指标。
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from metrics import summarize

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
TRACE_MARKER = "retrieval_trace "


def load_traces(log_path: Path) -> dict[str, list[dict]]:
    traces: dict[str, list[dict]] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            marker_index = line.find(TRACE_MARKER)
            if marker_index < 0:
                continue
            try:
                payload = json.loads(line[marker_index + len(TRACE_MARKER) :])
            except json.JSONDecodeError:
                continue
            conversation_id = payload.get("conversation_id")
            if conversation_id:
                traces.setdefault(conversation_id, []).append(payload)
    return traces


def ranked_values(traces: list[dict]) -> tuple[list[str], list[str]]:
    """按轨迹出现顺序去重，得到文件与片段的候选排名。"""
    documents: list[str] = []
    chunks: list[str] = []
    for trace in traces:
        for search in trace.get("searches", []):
            for item in search.get("fused", []):
                chunk_id = item.get("chunk_id")
                document_name = item.get("document_name")
                if document_name and document_name not in documents:
                    documents.append(document_name)
                if chunk_id and chunk_id not in chunks:
                    chunks.append(chunk_id)
    return documents, chunks


def attach_retrieval(records: list[dict], traces: dict[str, list[dict]]) -> int:
    missing = 0
    for record in records:
        conversation_id = record.get("conversation_id")
        conversation_traces = traces.get(conversation_id, []) if conversation_id else []
        documents, chunks = ranked_values(conversation_traces)
        record["retrieved_documents"] = documents
        record["retrieved_chunk_ids"] = chunks
        record["trace_count"] = len(conversation_traces)
        if conversation_traces:
            # 消融实验按策略分组统计，避免不同配置的记录混在一起平均。
            latest = conversation_traces[-1]
            record["retrieval_mode"] = latest.get("retrieval_mode", "")
            record["rerank_strategy"] = latest.get("rerank_strategy", "")
        if not conversation_traces:
            missing += 1
    return missing


def strategy_groups(records: list[dict]) -> dict[str, list[dict]]:
    """按 (召回模式 + 重排策略) 分组，供报告分列不同对照组。"""
    groups: dict[str, list[dict]] = {}
    for record in records:
        key = f"{record.get('retrieval_mode') or '未知'}/{record.get('rerank_strategy') or '未知'}"
        groups.setdefault(key, []).append(record)
    return groups


def write_report(
    records: list[dict],
    source_report: Path,
    log_path: Path,
    missing: int,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}-trace-{source_report.stem}"
    summary = summarize(records)
    groups = strategy_groups(records)
    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "log": str(log_path),
        "source_report": str(source_report),
        "missing_trace_cases": missing,
        "summary": summary,
        "strategy_groups": {
            key: summarize(group_records) for key, group_records in groups.items()
        },
        "records": records,
    }

    json_path = REPORTS_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 检索轨迹评测报告",
        "",
        f"- 运行时间：{payload['run_at']}",
        f"- 日志：{log_path}",
        f"- 来源报告：{source_report}",
        f"- 缺少轨迹的题目数：{missing}",
        "",
        "## 汇总（仅本次实际运行）",
        "",
    ]
    for key, value in summary.items():
        if value is not None:
            lines.append(f"- {key}: {value}")
    if any(key != "未知/未知" for key in groups):
        lines.extend(["", "## 分组对照（召回模式 / 重排策略）", ""])
        for key, group_records in sorted(groups.items()):
            lines.append(f"### {key}（{len(group_records)} 题）")
            lines.append("")
            for metric, value in summarize(group_records).items():
                if metric == "total" or value is None:
                    continue
                lines.append(f"- {metric}: {value}")
            lines.append("")
    lines.extend(["", "## 逐题检索排名", ""])
    for index, record in enumerate(records, start=1):
        lines.append(f"### {index}. {record['question']}")
        lines.append("")
        lines.append(f"- 类别：{record.get('category', '未分类')}")
        lines.append(f"- 轨迹条数：{record.get('trace_count', 0)}")
        lines.append(f"- 预期文件：{record.get('expected_files', [])}")
        lines.append(f"- 检索到文件：{record.get('retrieved_documents', [])}")
        lines.append(f"- 预期片段：{record.get('expected_chunk_ids', [])}")
        lines.append("")

    md_path = REPORTS_DIR / f"{stem}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="从检索轨迹日志计算 Recall@K/MRR")
    parser.add_argument("--log", type=Path, required=True, help="包含 retrieval_trace 的日志文件")
    parser.add_argument("--report", type=Path, required=True, help="run_evaluation.py 生成的 JSON 报告")
    args = parser.parse_args()

    if not args.log.exists():
        raise SystemExit(f"日志文件不存在：{args.log}")
    if not args.report.exists():
        raise SystemExit(f"报告文件不存在：{args.report}")

    payload = json.loads(args.report.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    traces = load_traces(args.log)
    missing = attach_retrieval(records, traces)
    report_path = write_report(records, args.report, args.log, missing)
    print(f"已写入轨迹评测报告：{report_path}")
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
