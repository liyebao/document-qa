import json
import logging
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.models.collection import Collection
from app.models.conversation import Conversation
from app.models.model_provider_config import ModelProviderConfig

if TYPE_CHECKING:
    from app.services.agent import DocumentQAAgent

trace_logger = logging.getLogger("retrieval_trace")


def log_retrieval_trace(
    conversation: Conversation,
    collection: Collection,
    agent: "DocumentQAAgent",
    *,
    query_count: int,
    tool_rounds: int,
    tool_retrieval_calls: int,
    tool_fallback: bool,
    document_filter_active: bool,
    document_filter_count: int,
    sub_question_coverage: list[bool],
    chat_config: ModelProviderConfig,
    retrieval_ms: float,
    answer_ms: float,
    status: str,
    cited_chunk_ids: list[str],
    error: str | None = None,
    document_scope_explicit: bool = False,
    rerank_model: str = "",
    rerank_fallback: bool = False,
    rerank_ms: float = 0.0,
) -> None:
    """输出结构化检索轨迹，供离线分析召回与耗时。

    不含资料正文与密钥；包含实际检索查询词（用户问题或其改写），
    用于区分"召回变了"还是"生成变了"。
    """
    settings = get_settings()
    payload = {
        "event": "retrieval_trace",
        "conversation_id": str(conversation.id),
        "collection_id": str(collection.id),
        "query_count": query_count,
        "tool_rounds": tool_rounds,
        "tool_retrieval_calls": tool_retrieval_calls,
        "tool_fallback": tool_fallback,
        "total_searches": len(agent.traces),
        # 检索策略快照：消融实验据此区分不同对照组，不必依赖当时的 .env。
        "retrieval_mode": settings.retrieval_mode,
        "rerank_strategy": settings.rerank_strategy,
        "llm_rerank_used": bool(getattr(agent, "llm_rerank_used", False)),
        "llm_rerank_ms": round(getattr(agent, "llm_rerank_ms", 0.0)),
        "llm_rerank_fallback": bool(getattr(agent, "llm_rerank_fallback", False)),
        "diversity_applied": bool(getattr(agent, "diversity_applied", False)),
        "expansion_rounds": int(getattr(agent, "expansion_rounds", 0)),
        "expansion_queries": int(getattr(agent, "expansion_queries", 0)),
        "document_filter_active": document_filter_active,
        "document_filter_count": document_filter_count,
        "document_scope_explicit": document_scope_explicit,
        "rerank_model": rerank_model,
        "rerank_fallback": rerank_fallback,
        "rerank_ms": round(rerank_ms),
        "sub_question_coverage": sub_question_coverage,
        "embedding_provider": collection.embedding_provider,
        "embedding_model": collection.embedding_model,
        "chat_provider": chat_config.provider_key,
        "chat_model": chat_config.chat_model,
        "retrieval_ms": round(retrieval_ms),
        "answer_ms": round(answer_ms),
        "status": status,
        "searches": [
            {
                "query_index": trace.query_index,
                "query": trace.query,
                "vector_candidates": trace.vector_candidates,
                "keyword_candidates": trace.keyword_candidates,
                "fused": trace.fused,
            }
            for trace in agent.traces
        ],
        "selected_chunk_ids": [str(item.chunk.id) for item in agent.evidence],
        "cited_chunk_ids": cited_chunk_ids,
    }
    if error:
        payload["error"] = error
    trace_logger.info("retrieval_trace %s", json.dumps(payload, ensure_ascii=False))
