"""回答自检的回归测试。"""

from app.services.answer_checks import (
    check_answer,
    dangling_references,
    leaked_markers,
    unsupported_code_lines,
)

EVIDENCE = [
    "用户管理速查 四类动作一张表 锁定 / 解锁 alter user ... account lock / unlock 见下一行说明 ",
    "create user u_limit identified by 'Vb@2026xyz' connection limit 3;",
]


def test_dangling_reference_is_reported():
    answer = "| 锁定 / 解锁 | alter user ... | 见下一行说明 |"
    assert dangling_references(answer) == ["见下一行"]


def test_dangling_reference_detects_multiple_forms_once():
    answer = "见上文，另见下表。"
    assert dangling_references(answer) == ["见上文", "见下表"]


def test_plain_answer_has_no_warnings():
    answer = "建用户会顺带建同名 schema，这是原生 PostgreSQL 没有的行为 [1]。"
    assert check_answer(answer, EVIDENCE) == []


def test_internal_retrieval_marker_is_reported():
    answer = "第七十一条各项见 紧接上文：[2]，并见下文见：[8]。"
    assert leaked_markers(answer) == ["下文见：", "紧接上文："]
    assert any("内部标记泄漏" in item for item in check_answer(answer, EVIDENCE))


def test_code_line_copied_verbatim_passes():
    answer = "```sql\ncreate user u_limit identified by 'Vb@2026xyz' connection limit 3;\n```"
    assert unsupported_code_lines(answer, EVIDENCE) == []


def test_code_line_with_rewritten_parameter_is_reported():
    answer = "```sql\ncreate user u_limit identified by 'Vb2026xyz' connection limit 3;\n```"
    missing = unsupported_code_lines(answer, EVIDENCE)
    assert len(missing) == 1
    assert "Vb2026xyz" in missing[0]


def test_comments_and_blank_lines_are_ignored():
    answer = "```sql\n-- 三个口令都满足 policy=1\n\nselect 1;\n```"
    missing = unsupported_code_lines(answer, EVIDENCE)
    assert missing == ["select 1;"]


def test_check_answer_combines_both_kinds():
    answer = (
        "见下一行说明 [1]\n\n"
        "```sql\ncreate user u_limit identified by 'Changed@2026';\n```"
    )
    warnings = check_answer(answer, EVIDENCE)
    assert any("悬空指代" in item for item in warnings)
    assert any("代码行不在被引片段里" in item for item in warnings)
