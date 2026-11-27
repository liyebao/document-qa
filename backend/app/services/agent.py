import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.secrets import read_secret
from app.core.text_utils import normalize_query as _normalize
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document
from app.models.model_provider_config import ModelProviderConfig
from app.services import embeddings, model_provider, query_intent
from app.services.locations import source_location
from app.services.retrieval import full_doc, reference_fill
from app.services.retrieval.bm25 import bm25_search
from app.services.retrieval.diversity import mmr_select
from app.services.retrieval.expansion import build_expansion_prompt, parse_terms
from app.services.retrieval.fusion import rrf_fuse
from app.services.retrieval.judgement import (
    MAX_SNIPPET_CHARS,
    build_judge_prompt,
    parse_keep_indices,
)
from app.services.retrieval.keyword import keyword_search
from app.services.retrieval.vector import vector_search

logger = logging.getLogger(__name__)

# 证据扩展产生的检索不计入任何子问题，用 -1 标记，避免污染子问题覆盖率。
EXPANSION_QUERY_INDEX = -1
# 按编号补证同理；能对上某个子问题时仍用真实编号，对不上才落到这里。
REFERENCE_QUERY_INDEX = -2
EXPANSION_SNIPPET_CHARS = 400
EXPANSION_SOURCE_LIMIT = 3


@dataclass
class EvidenceItem:
    index: int
    chunk: Chunk
    document: Document
    rrf_score: float
    rerank_score: float | None = None
    query_indices: set[int] = field(default_factory=set)
    # 同一份内容还出现在哪些文件里：重复上传时只保留一条正文，
    # 但来源要如实列出，否则回答看起来只依据了一个文件。
    also_in: set[str] = field(default_factory=set)
    # 分页把条文切成两段时，标记本条紧接哪一处依据；否则后段没有条号，模型认不出归属。
    continues: int | None = None


@dataclass
class SearchTrace:
    query_index: int
    # 实际执行的检索词：可能是规划改写、Agent 自主生成或证据扩展的术语。
    # 排查"同一问题两次结果不同"时需要它，否则无法区分是召回变了还是生成变了。
    query: str
    vector_candidates: list[str]
    keyword_candidates: list[str]
    fused: list[dict]


@dataclass
class _FillBudget:
    """按编号补证的预算：只限制总条数与总字符数。

    早先还限制单文件条数，但一个问题点名 3 条、而它们都在同一份条例里时，
    单文件上限会先把预算用完，最后一条的承接段反而补不进来；总预算已经
    足够约束上下文长度，不再按文件截断。
    """

    max_chunks: int
    max_chars: int
    chunks: int = 0
    chars: int = 0

    def allow(self, length: int) -> bool:
        if self.chunks >= self.max_chunks:
            return False
        return self.chars + length <= self.max_chars

    def consume(self, length: int) -> None:
        self.chunks += 1
        self.chars += length


def ready_documents(
    db: Session, collection: Collection
) -> list[tuple[uuid.UUID, str]]:
    rows = db.execute(
        select(Document.id, Document.filename).where(
            Document.collection_id == collection.id,
            Document.status == DOCUMENT_STATUS_READY,
            Document.deleted_at.is_(None),
            Document.is_enabled.is_(True),
            Document.is_current.is_(True),
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


def _load_entries(
    db: Session,
    chunk_ids: list[uuid.UUID],
    collection_id: uuid.UUID,
    document_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, tuple[Chunk, Document]]:
    if not chunk_ids:
        return {}
    conditions = [
        Chunk.id.in_(chunk_ids),
        Document.collection_id == collection_id,
        Document.status == DOCUMENT_STATUS_READY,
        Document.deleted_at.is_(None),
        Document.is_enabled.is_(True),
        Document.is_current.is_(True),
    ]
    if document_ids is not None:
        conditions.append(Document.id.in_(document_ids))
    rows = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(*conditions)
    ).all()
    return {chunk.id: (chunk, document) for chunk, document in rows}


def _truncate(text: str, limit: int) -> str:
    """压缩空白并截断，避免把整段原文塞进判证或扩展请求。"""
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


class DocumentQAAgent:
    """单 Agent：只暴露一个由后端注入用户与资料集范围的 search_documents 工具。

    Agent 不生成 SQL，也不持有权限条件；每次检索都强制限定当前用户、当前资料集、
    可用文件状态，以及用户问题中明确提到的文件名。
    """

    def __init__(
        self,
        db: Session,
        collection: Collection,
        embedding_config: ModelProviderConfig,
        document_ids: list[uuid.UUID] | None,
        *,
        rerank_config: ModelProviderConfig | None = None,
        rerank_query: str = "",
        chat_config: ModelProviderConfig | None = None,
    ) -> None:
        self.db = db
        self.collection = collection
        self.embedding_config = embedding_config
        self.document_ids = document_ids
        self.rerank_config = rerank_config
        self.rerank_query = rerank_query
        # 证据判证与查询扩展都需要回答模型；为空时自动跳过这两步。
        self.chat_config = chat_config
        self.rerank_ms = 0.0
        self.rerank_fallback = False
        self.rerank_scores: dict[uuid.UUID, float] = {}
        self.llm_rerank_used = False
        self.llm_rerank_ms = 0.0
        self.llm_rerank_fallback = False
        self.diversity_applied = False
        self.expansion_rounds = 0
        self.expansion_queries = 0
        self.full_scan_chunks = 0
        self.reference_chunks = 0
        self.evidence: list[EvidenceItem] = []
        self.traces: list[SearchTrace] = []
        self._ranked_lists: list[list[uuid.UUID]] = []
        self._chunks: dict[uuid.UUID, tuple[Chunk, Document]] = {}
        self._chunk_queries: dict[uuid.UUID, set[int]] = {}
        # 判证结果按片段累积，多轮选择时只对新增候选调用模型。
        self._judge_scores: dict[uuid.UUID, float] = {}
        # 向量路召回的原始相似度，仅供 trace/排错查看。
        self.vector_scores: dict[uuid.UUID, float] = {}
        # 已经检索过的查询，供证据扩展去重，避免重复召回同一批片段。
        self._executed_queries: set[str] = set()

    def _vector_candidates(self, query: str) -> list[uuid.UUID]:
        """向量路召回；维度与资料集索引不一致时直接失败，避免静默错配。"""
        settings = get_settings()
        vectors = embeddings.embed_texts(self.embedding_config, [query])
        if len(vectors) != 1:
            raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回数量不一致", 502)
        query_vector = vectors[0]
        if (
            self.collection.embedding_dimension is not None
            and len(query_vector) != self.collection.embedding_dimension
        ):
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                "当前 Embedding 模型维度与资料集索引不一致，请恢复原模型或重建索引",
                422,
            )
        pairs = vector_search(
            self.db,
            collection_id=self.collection.id,
            user_id=self.collection.user_id,
            query_vector=query_vector,
            limit=settings.retrieval_candidates,
            document_ids=self.document_ids,
            min_score=settings.retrieval_min_score,
        )
        # 相似度留档，便于排错时看清"为什么这块被召回/被丢弃"。
        self.vector_scores.update(pairs)
        return [chunk_id for chunk_id, _ in pairs]

    def _keyword_candidates(self, query: str) -> list[uuid.UUID]:
        """关键词路召回；分词全部未命中时回退子串匹配。"""
        settings = get_settings()
        candidates = bm25_search(
            self.db,
            collection_id=self.collection.id,
            user_id=self.collection.user_id,
            query=query,
            limit=settings.retrieval_candidates,
            document_ids=self.document_ids,
        )
        if candidates:
            return candidates
        # 分词后无命中（专有名词被切碎、纯符号等）时回退子串匹配。
        return keyword_search(
            self.db,
            collection_id=self.collection.id,
            user_id=self.collection.user_id,
            query=query,
            limit=settings.retrieval_candidates,
            document_ids=self.document_ids,
        )

    def search_documents(self, query: str, *, query_index: int = 0) -> list[uuid.UUID]:
        settings = get_settings()
        mode = settings.retrieval_mode
        self._executed_queries.add(_normalize(query))
        vector_candidates: list[uuid.UUID] = []
        keyword_candidates: list[uuid.UUID] = []
        if mode != "keyword":
            vector_candidates = self._vector_candidates(query)
        if mode != "vector":
            keyword_candidates = self._keyword_candidates(query)
        ranked_lists = [
            candidates
            for candidates in (vector_candidates, keyword_candidates)
            if candidates
        ]
        fused = (
            rrf_fuse(ranked_lists, k=settings.rrf_k) if ranked_lists else []
        )
        loaded = _load_entries(
            self.db,
            [chunk_id for chunk_id, _ in fused],
            self.collection.id,
            self.document_ids,
        )
        self._ranked_lists.extend([vector_candidates, keyword_candidates])
        self._chunks.update(loaded)
        for chunk_id in {*vector_candidates, *keyword_candidates}:
            self._chunk_queries.setdefault(chunk_id, set()).add(query_index)

        fused_payload = []
        for chunk_id, score in fused:
            entry = loaded.get(chunk_id)
            fused_payload.append(
                {
                    "chunk_id": str(chunk_id),
                    "document_id": str(entry[1].id) if entry else None,
                    "document_name": entry[1].filename if entry else None,
                    "rrf_score": round(score, 6),
                }
            )
        self.traces.append(
            SearchTrace(
                query_index=query_index,
                query=query,
                vector_candidates=[str(chunk_id) for chunk_id in vector_candidates],
                keyword_candidates=[str(chunk_id) for chunk_id in keyword_candidates],
                fused=fused_payload,
            )
        )
        return [chunk_id for chunk_id, _ in fused]

    def search_planned_queries(self, queries: list[str], executed: dict[str, int]) -> None:
        """按子问题逐条检索，并补一次规范化问法。

        同义的问法（「第71条第2项」「71条第二项」「article 71 item 2」）经
        query_intent 归一后落到同一标准问法；补这一次能让召回不受措辞影响，
        又不会给每个子问题引入新的编号。executed 与工具循环共用同一张表。
        """
        settings = get_settings()
        for index, query in enumerate(queries):
            variants = (
                query_intent.expand_queries(query, limit=settings.query_variants_max)
                if settings.query_variants_enabled
                else [query]
            )
            for text in variants:
                key = _normalize(text)
                if key in executed:
                    continue
                self.search_documents(text, query_index=index)
                executed[key] = index

    def format_search_preview(self, chunk_ids: list[uuid.UUID], limit: int = 3) -> str:
        """给 Agent 的检索预览，不分配最终引用编号。"""
        lines: list[str] = []
        for chunk_id in chunk_ids[:limit]:
            entry = self._chunks.get(chunk_id)
            if entry is None:
                continue
            chunk, document = entry
            text = re.sub(r"\s+", " ", chunk.text).strip()
            if len(text) > 300:
                text = text[:300] + "…"
            lines.append(f"- 《{document.filename}》{source_location(chunk)}：{text}")
        return "\n".join(lines)

    def select_evidence(self) -> list[EvidenceItem]:
        """对所有子问题的召回统一做 RRF，再按策略重排并做多样性选择。"""
        settings = get_settings()
        fused = rrf_fuse(self._ranked_lists, k=settings.rrf_k)
        candidates = fused[: settings.rerank_candidates]

        if candidates:
            reranked = self._apply_rerank(candidates)
            if reranked is not None:
                candidates = reranked
            candidates = self._apply_diversity(candidates)

        evidence: list[EvidenceItem] = []
        seen_fingerprints: dict[str, EvidenceItem] = {}
        for chunk_id, score in candidates:
            if len(evidence) >= settings.retrieval_top_k:
                break
            entry = self._chunks.get(chunk_id)
            if entry is None:
                continue
            # 同一份内容重复入库时，fingerprint 相同；只保留排名最高的一份，
            # 但要把另一份文件的文件名记在证据上，回答才能说明它也有这份内容。
            fingerprint = entry[0].fingerprint
            if fingerprint:
                kept = seen_fingerprints.get(fingerprint)
                if kept is not None:
                    self._note_duplicate(kept, entry[1])
                    continue
            item = EvidenceItem(
                index=len(evidence) + 1,
                chunk=entry[0],
                document=entry[1],
                rrf_score=score,
                rerank_score=self.rerank_scores.get(chunk_id),
                query_indices=set(self._chunk_queries.get(chunk_id, set())),
            )
            if fingerprint:
                seen_fingerprints[fingerprint] = item
            evidence.append(item)
        self.evidence = evidence
        return evidence

    def _apply_rerank(
        self, candidates: list[tuple[uuid.UUID, float]]
    ) -> list[tuple[uuid.UUID, float]] | None:
        """按配置分派重排策略；返回 None 表示维持 RRF 顺序。"""
        strategy = get_settings().rerank_strategy
        if strategy == "off":
            return None
        if strategy == "llm":
            scores = self._llm_judge(candidates)
        else:
            if self.rerank_config is None or not self.rerank_config.rerank_model:
                return None
            scores = self._rerank(candidates)
        if scores is None:
            return None
        # 同分时保留 RRF 原顺序：判证结果是二值的，用 UUID 兜底会打乱保留项的先后。
        order = {chunk_id: index for index, (chunk_id, _) in enumerate(candidates)}
        ordered = sorted(
            candidates,
            key=lambda item: (-scores.get(item[0], float("-inf")), order[item[0]]),
        )
        # 判证一条都没保留：返回空候选，让上层如实回答"资料里没有"，
        # 而不是把 0 分片段按 RRF 顺序硬塞进上下文。
        if all(scores.get(chunk_id, 0.0) <= 0.0 for chunk_id, _ in ordered):
            return []
        return ordered

    def _apply_diversity(
        self, candidates: list[tuple[uuid.UUID, float]]
    ) -> list[tuple[uuid.UUID, float]]:
        """MMR 多样性选择；候选文件不足时按原分数回补，不会让上下文变短。"""
        settings = get_settings()
        if not settings.diversity_enabled:
            return candidates
        vectors: dict[uuid.UUID, list[float] | None] = {}
        document_ids: dict[uuid.UUID, uuid.UUID] = {}
        for chunk_id, _ in candidates:
            entry = self._chunks.get(chunk_id)
            if entry is None:
                continue
            vectors[chunk_id] = entry[0].embedding
            document_ids[chunk_id] = entry[1].id
        selected = mmr_select(
            candidates,
            vectors=vectors,
            document_ids=document_ids,
            limit=settings.retrieval_top_k,
            lambda_=settings.mmr_lambda,
            max_per_document=settings.mmr_max_per_document,
        )
        original = [chunk_id for chunk_id, _ in candidates[: len(selected)]]
        self.diversity_applied = [chunk_id for chunk_id, _ in selected] != original
        return selected

    def _rerank(
        self, candidates: list[tuple[uuid.UUID, float]]
    ) -> dict[uuid.UUID, float] | None:
        """调用重排模型；任何失败都返回 None，由调用方回退 RRF 顺序。"""
        if self.rerank_config is None or not self.rerank_config.rerank_model:
            return None
        chunk_ids: list[uuid.UUID] = []
        documents: list[str] = []
        for chunk_id, _ in candidates:
            if chunk_id in self.rerank_scores:
                continue  # 多轮选择时只对新增候选调用重排
            entry = self._chunks.get(chunk_id)
            if entry is None:
                continue
            chunk_ids.append(chunk_id)
            # 2000 字符对中文只有约 1000 token，块尾会完全丢失精排信号。
            documents.append(entry[0].text[:6000])
        if not documents:
            return dict(self.rerank_scores) or None

        spec = model_provider.get_provider_spec(self.rerank_config.provider_key)
        api_key = read_secret(
            self.rerank_config.api_key_ciphertext, self.rerank_config.key_version
        )
        started = time.perf_counter()
        try:
            results = model_provider.request_rerank(
                spec,
                api_key,
                self.rerank_config.rerank_model,
                self.rerank_query,
                documents,
                len(documents),
            )
        except AppError as exc:
            self.rerank_fallback = True
            logger.warning("重排失败，回退 RRF 排序：%s", exc.code)
            return None
        finally:
            self.rerank_ms = (time.perf_counter() - started) * 1000

        scores: dict[uuid.UUID, float] = {}
        for index, score in results:
            if 0 <= index < len(chunk_ids):
                scores[chunk_ids[index]] = score
        if not scores:
            self.rerank_fallback = True
            return None
        self.rerank_scores.update(scores)
        return dict(self.rerank_scores)

    def _llm_judge(
        self, candidates: list[tuple[uuid.UUID, float]]
    ) -> dict[uuid.UUID, float] | None:
        """用回答模型批量做二元证据判证，作为 rerank 模型的零依赖替代。

        返回 {片段: 1.0 保留 / 0.0 剔除}；模型不可用或输出异常时返回 None。
        """
        if self.chat_config is None or not self.chat_config.chat_model:
            return None
        chunk_ids: list[uuid.UUID] = []
        snippets: list[str] = []
        for chunk_id, _ in candidates:
            if chunk_id in self._judge_scores:
                continue  # 多轮选择时只判证新增候选
            entry = self._chunks.get(chunk_id)
            if entry is None:
                continue
            chunk_ids.append(chunk_id)
            snippets.append(
                f"[{len(chunk_ids)}] 《{entry[1].filename}》{source_location(entry[0])}\n"
                f"{_truncate(entry[0].text, MAX_SNIPPET_CHARS)}"
            )
        if not snippets:
            return dict(self._judge_scores) or None

        spec = model_provider.get_provider_spec(self.chat_config.provider_key)
        api_key = read_secret(
            self.chat_config.api_key_ciphertext, self.chat_config.key_version
        )
        started = time.perf_counter()
        try:
            raw = model_provider.chat_completion(
                spec,
                api_key,
                self.chat_config.chat_model,
                build_judge_prompt(self.rerank_query, snippets),
                temperature=0,
                max_tokens=200,
            )
            keep = parse_keep_indices(raw, len(chunk_ids))
        except AppError as exc:
            logger.warning("LLM 判证失败，回退 RRF 排序：%s", exc.code)
            self.llm_rerank_fallback = True
            self.llm_rerank_ms += (time.perf_counter() - started) * 1000
            return None
        self.llm_rerank_ms += (time.perf_counter() - started) * 1000
        if keep is None:
            self.llm_rerank_fallback = True
            return None

        kept = {chunk_ids[index - 1] for index in keep}
        for chunk_id in chunk_ids:
            self._judge_scores[chunk_id] = 1.0 if chunk_id in kept else 0.0
        self.llm_rerank_used = True
        return dict(self._judge_scores)

    def expand_from_evidence(
        self,
        chat_config: ModelProviderConfig | None,
        question: str,
        *,
        max_terms: int,
    ) -> list[str]:
        """从当前证据里抽取术语并补充检索，返回实际执行的扩展查询。"""
        if chat_config is None or not chat_config.chat_model or not self.evidence:
            return []
        snippets = [
            f"[{item.index}] 《{item.document.filename}》{source_location(item.chunk)}\n"
            f"{_truncate(item.chunk.text, EXPANSION_SNIPPET_CHARS)}"
            for item in self.evidence[:EXPANSION_SOURCE_LIMIT]
        ]
        spec = model_provider.get_provider_spec(chat_config.provider_key)
        api_key = read_secret(chat_config.api_key_ciphertext, chat_config.key_version)
        try:
            raw = model_provider.chat_completion(
                spec,
                api_key,
                chat_config.chat_model,
                build_expansion_prompt(question, snippets, max_terms),
                temperature=0,
                max_tokens=200,
            )
        except AppError as exc:
            logger.warning("证据扩展失败，跳过本轮扩展：%s", exc.code)
            return []
        terms = parse_terms(raw, max_terms=max_terms)
        executed: list[str] = []
        for term in terms:
            if _normalize(term) in self._executed_queries:
                continue
            try:
                self.search_documents(term, query_index=EXPANSION_QUERY_INDEX)
            except AppError as exc:
                # 扩展只是补充召回，失败时保留已有结果，不让整次回答失败。
                logger.warning("证据扩展检索失败，结束本轮扩展：%s", exc.code)
                break
            executed.append(term)
        self.expansion_queries += len(executed)
        return executed

    def expand_evidence_for_full_document(self) -> int:
        """补齐命中文档的原文序列，供计数/全量类问题核对首尾与缺口。"""
        settings = get_settings()
        document_ids = list(dict.fromkeys(item.document.id for item in self.evidence))
        rows = full_doc.fetch_document_chunks(
            self.db,
            collection_id=self.collection.id,
            document_ids=document_ids,
            limit=max(1, settings.full_scan_max_chunks),
        )
        existing = {item.chunk.id for item in self.evidence}
        by_fingerprint = {
            item.chunk.fingerprint: item
            for item in self.evidence
            if item.chunk.fingerprint
        }
        total_chars = sum(len(item.chunk.text or "") for item in self.evidence)
        added = 0
        for chunk, document in rows:
            if chunk.id in existing:
                continue
            if chunk.fingerprint and chunk.fingerprint in by_fingerprint:
                self._note_duplicate(by_fingerprint[chunk.fingerprint], document)
                continue
            length = len(chunk.text or "")
            if total_chars + length > settings.full_scan_max_chars:
                break
            self._chunks[chunk.id] = (chunk, document)
            self._chunk_queries.setdefault(chunk.id, set()).add(EXPANSION_QUERY_INDEX)
            item = EvidenceItem(
                index=len(self.evidence) + 1,
                chunk=chunk,
                document=document,
                rrf_score=0.0,
                query_indices={EXPANSION_QUERY_INDEX},
            )
            self.evidence.append(item)
            existing.add(chunk.id)
            if chunk.fingerprint:
                by_fingerprint[chunk.fingerprint] = item
            total_chars += length
            added += 1
        self.full_scan_chunks += added
        return added

    def fill_missing_references(self, question: str) -> int:
        """问题点名结构编号时，把证据里缺失的编号原文补齐。

        编号在资料集中可能出现在多份文件里，也可能被分页切成「编号 + 引导句」
        和分项列举两段；检索的 top_k 只能命中其中一部分，模型就会答「无法确认」。
        这里统一按「文件 + 编号」判断缺什么：先补缺失编号的原文，再按窗口补齐
        被切开的后续片段，并挂到问该编号的子问题上。
        """
        settings = get_settings()
        if not settings.reference_fill_enabled:
            return 0
        intent = query_intent.understand(question)
        references = list(intent.references)
        if not references or not self.evidence:
            return 0

        span = max(1, settings.reference_fill_continuation_span)
        # 点名到「第Y项」时，整条原文常跨好几个片段，按窗口取回而不是只看冒号。
        force_window = bool(intent.items)
        if force_window:
            span = max(span, 2)
        covered, seeds = self._reference_seeds(references, force=force_window)
        budget = _FillBudget(
            max_chunks=settings.reference_fill_max_chunks,
            max_chars=settings.reference_fill_max_chars,
        )
        existing = {item.chunk.id for item in self.evidence}
        added = 0

        rows = reference_fill.fetch_reference_chunks(
            self.db,
            collection_id=self.collection.id,
            references=references,
            document_ids=self.document_ids,
            limit=budget.max_chunks * 3,
        )
        for chunk, document in rows:
            text = chunk.text or ""
            missing = reference_fill.references_in(text, references) - covered.get(
                document.id, set()
            )
            if not missing or chunk.id in existing:
                continue
            if not budget.allow(len(text)):
                continue
            query_indices = self._link_queries(text, sorted(missing)) or {
                REFERENCE_QUERY_INDEX
            }
            self._add_reference_evidence(chunk, document, query_indices, None)
            covered.setdefault(document.id, set()).update(missing)
            existing.add(chunk.id)
            budget.consume(len(text))
            added += 1
            if force_window or reference_fill.needs_continuation(text):
                seeds.append((chunk, set(query_indices), len(self.evidence)))

        for chunk, document in reference_fill.fetch_continuation_chunks(
            self.db,
            collection_id=self.collection.id,
            seeds=[(seed.document_id, seed.ordinal) for seed, _, _ in seeds],
            span=span,
        ):
            if chunk.id in existing:
                continue
            if not budget.allow(len(chunk.text or "")):
                continue
            query_indices, continues = self._continuation_source(chunk, seeds, span)
            self._add_reference_evidence(
                chunk,
                document,
                query_indices or {REFERENCE_QUERY_INDEX},
                continues,
            )
            existing.add(chunk.id)
            budget.consume(len(chunk.text or ""))
            added += 1

        self.reference_chunks += added
        return added

    def _reference_seeds(
        self, references: list[reference_fill.Reference], *, force: bool = False
    ) -> tuple[dict[uuid.UUID, set[str]], list[tuple[Chunk, set[int], int]]]:
        """统计「文件 + 编号」覆盖度，并挑出需要接续的片段作为承接起点。"""
        covered: dict[uuid.UUID, set[str]] = {}
        seeds: list[tuple[Chunk, set[int], int]] = []
        for item in self.evidence:
            text = item.chunk.text or ""
            present = reference_fill.references_in(text, references)
            if not present:
                continue
            covered.setdefault(item.document.id, set()).update(present)
            if force or reference_fill.needs_continuation(text):
                seeds.append(
                    (
                        item.chunk,
                        set(item.query_indices) or {REFERENCE_QUERY_INDEX},
                        item.index,
                    )
                )
        return covered, seeds

    @staticmethod
    def _note_duplicate(item: EvidenceItem, document: Document) -> None:
        """同一段原文也出现在另一份文件里：不重复占预算，但来源要如实记下。"""
        if item.document.id != document.id:
            item.also_in.add(document.filename)

    def _add_reference_evidence(
        self,
        chunk: Chunk,
        document: Document,
        query_indices: set[int],
        continues: int | None,
    ) -> None:
        self._chunks[chunk.id] = (chunk, document)
        self._chunk_queries.setdefault(chunk.id, set()).update(query_indices)
        self.evidence.append(
            EvidenceItem(
                index=len(self.evidence) + 1,
                chunk=chunk,
                document=document,
                rrf_score=0.0,
                query_indices=set(query_indices),
                continues=continues,
            )
        )

    def _continuation_source(
        self,
        chunk: Chunk,
        seeds: list[tuple[Chunk, set[int], int]],
        span: int,
    ) -> tuple[set[int], int | None]:
        """找承接片段最近的种子，返回它对应的子问题与种子编号。"""
        best: tuple[int, set[int], int] | None = None
        for seed, queries, index in seeds:
            gap = chunk.ordinal - seed.ordinal
            if seed.document_id != chunk.document_id or not 0 < gap <= span:
                continue
            if best is None or gap < best[0]:
                best = (gap, queries, index)
        if best is None:
            return set(), None
        return best[1], best[2]

    def _link_queries(self, text: str, labels: list[str]) -> set[int]:
        """把补证内容挂到问同一编号的子问题上；对不上时由调用方标记为无主证据。"""
        wanted = set(labels)
        linked: set[int] = set()
        for trace in self.traces:
            if trace.query_index < 0:
                continue
            traced = {
                reference.label
                for reference in reference_fill.extract_references(trace.query)
            }
            if traced & wanted:
                linked.add(trace.query_index)
        return linked

    def coverage(self, query_count: int) -> list[bool]:
        covered: set[int] = set()
        for item in self.evidence:
            covered.update(item.query_indices)
        return [index in covered for index in range(query_count)]

    def build_context(self) -> str:
        parts: list[str] = []
        # 分页会把条文切成相邻两段；标出前后关系，模型才认得出没有条号的那半段。
        positions = {
            (item.document.id, item.chunk.ordinal): item.index for item in self.evidence
        }
        for item in self.evidence:
            # 章节要带完整层级：只给最后一级时，模型分不清「5.1 用户管理」和
            # 「5.2 权限管理」，容易把后一节的注意事项并到前一节里。
            section = item.chunk.heading_path.strip()
            section_part = f"｜章节：{section}" if section else ""
            linked = [str(index + 1) for index in sorted(item.query_indices) if index >= 0]
            linked_part = f"｜关联问题：{'、'.join(linked)}" if linked else ""
            previous = item.continues or positions.get(
                (item.document.id, item.chunk.ordinal - 1)
            )
            continues_part = (
                f"｜紧接上文：[{previous}]"
                if previous and previous != item.index
                else ""
            )
            following = positions.get((item.document.id, item.chunk.ordinal + 1))
            following_part = f"｜下文见：[{following}]" if following else ""
            also_part = ""
            if item.also_in:
                names = "、".join(f"《{name}》" for name in sorted(item.also_in))
                also_part = f"｜同文另见：{names}"
            parts.append(
                f"[{item.index}]"
                f"｜文件：{item.document.filename}"
                f"｜位置：{source_location(item.chunk)}{section_part}{linked_part}"
                f"{continues_part}{following_part}{also_part}"
                f"\n{item.chunk.text}"
            )
        return "\n\n".join(parts)

    def cited_chunk_ids(self, indices: list[int]) -> list[str]:
        return [
            str(self.evidence[index - 1].chunk.id)
            for index in indices
            if 1 <= index <= len(self.evidence)
        ]
