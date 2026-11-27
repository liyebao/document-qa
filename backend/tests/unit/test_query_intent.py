"""问法归一化：同一意图的不同说法必须得到同一个检索路径。"""

from types import SimpleNamespace

from app.services import query_intent
from app.services.agent import DocumentQAAgent


def _agent() -> DocumentQAAgent:
    agent = DocumentQAAgent.__new__(DocumentQAAgent)
    agent.db = None
    agent.collection = SimpleNamespace(id=None, user_id=None)
    agent.document_ids = None
    agent.evidence = []
    agent.traces = []
    agent._chunks = {}
    agent._chunk_queries = {}
    return agent


# ------------------------------------------------------------ 同义问法


PARAPHRASES = [
    "第七十一条第2项的内容是什么？",
    "第七十一条第二项怎么规定的",
    "第71条第2项写了啥",
    "71条第二项说的是什么",
    "71 条 第 2 项 的原文",
    "第７１条第２项",
    "第七十一条 第（二）项",
    "第七十一条的第二个分项是什么",
    "article 71 item 2 的内容",
    "clause 71(2) 规定",
]


def test_paraphrases_share_one_intent_key() -> None:
    keys = {query_intent.understand(text).key for text in PARAPHRASES}
    assert len(keys) == 1, keys
    assert keys.pop() == "content|第七十一条|第二项"


def test_count_paraphrases_share_one_intent_key() -> None:
    questions = [
        "这份条例总共有多少条？",
        "条例一共几条",
        "全文多少条",
        "条数是多少",
        "how many articles does it have",
    ]
    assert {query_intent.understand(text).key for text in questions} == {"count"}


def test_last_article_paraphrases_share_one_intent_key() -> None:
    questions = ["最后一条是什么", "末条内容", "最后条文怎么规定", "last article 是什么"]
    assert {query_intent.understand(text).key for text in questions} == {"last"}


def test_different_intents_do_not_collide() -> None:
    assert query_intent.understand("19条").key != query_intent.understand("共有多少条").key


# ------------------------------------------------------------ 结构抽取


def test_item_forms_are_normalized() -> None:
    cases = {
        "第33条第3项": ("第三项",),
        "第33条第三项": ("第三项",),
        "第33条（三）": ("第三项",),
        "article 33(3)": ("第三项",),
        "article 33 item 3": ("第三项",),
        "第33条的第三个小项": ("第三项",),
    }
    for text, expected in cases.items():
        assert query_intent.understand(text).items == expected, text


def test_leading_zeros_and_fullwidth_digits() -> None:
    assert query_intent.understand("02条的内容").key == "content|第二条"
    assert query_intent.understand("１９条").key == "content|第十九条"


def test_zero_padded_english_numbers() -> None:
    intent = query_intent.understand("article 033")
    assert intent.references[0].label == "第三十三条"


# ------------------------------------------------------------ 检索扩展


def test_expand_queries_keeps_original_and_caps_variants() -> None:
    expanded = query_intent.expand_queries("第33条第3项写了啥", limit=1)
    assert expanded[0] == "第33条第3项写了啥"
    assert len(expanded) == 2
    assert "第三十三条" in expanded[1]


def test_expand_queries_skips_variants_for_multi_reference() -> None:
    assert query_intent.expand_queries("71条第2项、62条第2项、19条") == [
        "71条第2项、62条第2项、19条"
    ]


def test_expand_queries_can_be_disabled_by_zero_limit() -> None:
    assert query_intent.expand_queries("第33条第3项", limit=0) == ["第33条第3项"]


def test_alignment_hint_covers_article_and_item_forms() -> None:
    hint = query_intent.alignment_hint("第七十一条第2项")
    assert "第二项" in hint
    assert "（二）" in hint
    assert "第七十一条" in hint

    article = query_intent.alignment_hint("02条讲什么")
    assert "第二条" in article

    assert query_intent.alignment_hint("这份条例有多少条") == ""


def test_search_planned_queries_runs_variant_under_same_sub_question(
    monkeypatch,
) -> None:
    agent = _agent()
    calls: list[tuple[str, int]] = []
    agent.search_documents = lambda text, query_index=0: calls.append((text, query_index))
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: SimpleNamespace(query_variants_enabled=True, query_variants_max=1),
    )

    agent.search_planned_queries(["第33条第3项写了啥"], {})

    assert calls[0] == ("第33条第3项写了啥", 0)
    assert calls[1][1] == 0
    assert "第三十三条" in calls[1][0]


def test_search_planned_queries_respects_disabled_setting(monkeypatch) -> None:
    agent = _agent()
    calls: list[str] = []
    agent.search_documents = lambda text, query_index=0: calls.append(text)
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: SimpleNamespace(query_variants_enabled=False, query_variants_max=1),
    )

    agent.search_planned_queries(["第33条第3项"], {})

    assert calls == ["第33条第3项"]
