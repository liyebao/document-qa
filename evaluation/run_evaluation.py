"""通过后端 API 运行离线问题集，记录实际回答、引用和拒答情况。

用法（先在 backend 虚拟环境中安装依赖；单用户模式无需登录）：
    backend\\.venv\\Scripts\\python evaluation\\run_evaluation.py ^
        --collection-id <资料集 ID> --dataset evaluation\\dataset.example.jsonl

结果写入 evaluation/reports/，报告只记录本次实际运行数据，不预设指标结论。
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx

from metrics import summarize

DEFAULT_BASE_URL = "http://localhost:8000"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def load_dataset(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"数据集第 {line_number} 行不是合法 JSON：{exc}") from exc
    return records


def run_case(
    client: httpx.Client,
    collection_id: str,
    case: dict,
) -> dict:
    record = {
        "question": case["question"],
        "category": case.get("category", "未分类"),
        "expected_refusal": bool(case.get("expected_refusal", False)),
        "expected_points": case.get("expected_points", []),
        "expected_evidence": case.get("expected_evidence", []),
        "expected_files": case.get("expected_files", []),
        "expected_chunk_ids": case.get("expected_chunk_ids", []),
        "conversation_id": None,
    }
    try:
        conversation = client.post(
            f"/api/collections/{collection_id}/conversations",
            json={},
        )
        conversation.raise_for_status()
        conversation_id = conversation.json()["id"]
        record["conversation_id"] = conversation_id

        answer = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": case["question"]},
        )
        answer.raise_for_status()
        assistant = answer.json()["assistant_message"]
        record.update(
            {
                "answer": assistant["content"],
                "status": assistant["status"],
                "citations": [
                    {
                        "chunk_id": citation["chunk_id"],
                        "document_id": citation.get("document_id"),
                        "document_name": citation["document_name"],
                        "source_location": citation["source_location"],
                    }
                    for citation in assistant["citations"]
                ],
            }
        )
    except httpx.HTTPError as exc:
        record.update({"error": str(exc), "answer": "", "citations": []})
    return record


def write_report(records: list[dict], dataset: Path, base_url: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"{stamp}-api-{dataset.stem}"

    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "dataset": str(dataset),
        "summary": summarize(records),
        "records": records,
    }
    json_path = REPORTS_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 评测报告",
        "",
        f"- 运行时间：{payload['run_at']}",
        f"- 后端地址：{base_url}",
        f"- 数据集：{dataset}",
        "",
        "## 汇总（仅本次实际运行）",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 逐题记录", ""])
    for index, record in enumerate(records, start=1):
        lines.append(f"### {index}. {record['question']}")
        lines.append("")
        lines.append(f"- 类别：{record['category']}")
        lines.append(f"- 预期拒答：{record['expected_refusal']}")
        if record.get("error"):
            lines.append(f"- 运行错误：{record['error']}")
        lines.append(f"- 实际回答：{record.get('answer', '')}")
        lines.append(f"- 引用：{record.get('citations', [])}")
        lines.append("")

    md_path = REPORTS_DIR / f"{stem}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="运行离线问答评测")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--collection-id", required=True)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/dataset.example.jsonl"))
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    with httpx.Client(base_url=args.base_url, timeout=180.0) as client:
        records = [run_case(client, args.collection_id, case) for case in dataset]

    report_path = write_report(records, args.dataset, args.base_url)
    print(f"已写入评测报告：{report_path}")
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
