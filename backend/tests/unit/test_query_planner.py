from uuid import UUID

from app.services.query_planner import (
    extract_document_ids,
    looks_compound,
    looks_followup,
    parse_queries,
)

DOC_A = UUID("00000000-0000-0000-0000-0000000000a1")
DOC_B = UUID("00000000-0000-0000-0000-0000000000b2")


def test_extract_document_ids_matches_explicit_filename() -> None:
    documents = [(DOC_A, "项目风险报告.pdf"), (DOC_B, "预算说明.docx")]
    assert extract_document_ids(
        "请只根据项目风险报告.pdf 回答", documents
    ) == [DOC_A]


def test_extract_document_ids_matches_long_stem() -> None:
    documents = [(DOC_A, "2026年度项目风险报告.pdf")]
    assert extract_document_ids("2026年度项目风险报告里怎么说的？", documents) == [DOC_A]


def test_extract_document_ids_ignores_short_or_absent_names() -> None:
    documents = [(DOC_A, "报告.pdf"), (DOC_B, "预算说明.docx")]
    assert extract_document_ids("报告中提到了什么？", documents) is None


def test_extract_document_ids_returns_empty_for_missing_explicit_file() -> None:
    documents = [(DOC_A, "项目风险报告.pdf")]
    assert extract_document_ids("请根据不存在.pdf 回答", documents) == []


def test_extract_document_ids_is_case_insensitive() -> None:
    documents = [(DOC_A, "Annual-Report.pdf")]
    assert extract_document_ids("annual-report.pdf 的结论", documents) == [DOC_A]


def test_parse_queries_reads_json() -> None:
    raw = '{"queries": ["第一个子问题", "第二子问题"]}'
    assert parse_queries(raw, "原问题") == ["第一个子问题", "第二子问题"]


def test_parse_queries_tolerates_code_fence() -> None:
    raw = '```json\n{"queries": ["改写后的问题"]}\n```'
    assert parse_queries(raw, "原问题") == ["改写后的问题"]


def test_parse_queries_falls_back_on_invalid_output() -> None:
    assert parse_queries("不是 JSON", "原问题") == ["原问题"]
    assert parse_queries('{"queries": []}', "原问题") == ["原问题"]
    assert parse_queries('{"queries": ["", "有效问题"]}', "原问题") == ["有效问题"]


def test_parse_queries_limits_count() -> None:
    raw = '{"queries": ["一", "二", "三", "四", "五"]}'
    assert len(parse_queries(raw, "原问题")) == 4


def test_looks_compound_detects_markers() -> None:
    assert looks_compound("分别说明两份报告的结论以及风险")
    assert not looks_compound("项目的主要风险是什么")


def test_looks_followup_detects_pronouns() -> None:
    assert looks_followup("它后来怎么样了？")
    assert looks_followup("那么这份报告的数据呢？")
    assert not looks_followup("项目的主要风险是什么")


def test_looks_followup_skips_long_self_contained_question() -> None:
    question = "这个项目在进度、成本、质量和人员方面存在哪些主要风险以及分别有哪些应对措施？"
    assert not looks_followup(question)
