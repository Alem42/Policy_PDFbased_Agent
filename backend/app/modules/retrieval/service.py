from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.ai.budget import BudgetExceeded
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.service import (
    documents_have_embeddings,
    read_documents,
    resolve_document_ids,
    retrieve_relevant_chunks,
    search_full_corpus,
)
from app.modules.embedding import service as embedding
from app.modules.evidence_validation import service as evidence_validation
from app.modules.reranking import service as reranking
from app.modules.retrieval.contracts import (
    EvidenceDecision,
    QuestionValidationRequest,
    RetrievalRequest,
    RetrievalResult,
)
from app.modules.retrieval.coverage import allocate
from app.modules.retrieval.evidence import (
    assess_evidence_sufficiency,
    is_chunk_relevant,
    max_vector_distance,
    min_reranker_score,
)
from app.modules.retrieval.formatting import format_context
from app.modules.retrieval.metadata_filters import FilterApplication, metadata_filter_service
from app.modules.usage.context import bind

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve, format, cite, and evidence-gate knowledge in one call.

    This synchronous black box is safe to call from worker threads. It owns no
    HTTP or LangGraph state, so Direct, ReAct, suggestions, scripts, and tests
    can share exactly the same retrieval semantics.
    """

    def load_pages(self, identifiers: list[str], *, include_restricted: bool = False) -> list[dict]:
        return read_documents(identifiers, include_restricted=include_restricted)

    def retrieve(
        self,
        request: RetrievalRequest,
        *,
        preloaded_pages: list[dict] | None = None,
    ) -> RetrievalResult:
        if not request.question.strip():
            raise ValueError("Retrieval question must not be blank.")
        guard_config = evidence_validation.config()
        if request.top_k <= 0:
            raise ValueError("Retrieval top_k must be greater than zero.")
        if request.scope == "selected" and not request.identifiers:
            raise ValueError("Selected-document retrieval requires at least one document.")

        identifiers = list(request.identifiers)
        filter_application = (
            metadata_filter_service.apply(
                request.metadata_filters,
                scope=request.scope,
                identifiers=identifiers,
                include_restricted=request.include_restricted,
            )
            if request.metadata_filters.active
            else FilterApplication(tuple(identifiers))
        )
        effective_identifiers = list(filter_application.document_ids)
        if request.metadata_filters.active and not effective_identifiers:
            return RetrievalResult(
                evidence=EvidenceDecision(
                    False, "No documents match the explicit metadata filters."
                ),
                filter_applied=True,
                filter_notice=filter_application.notice,
            )
        if request.scope == "selected":
            pages = (
                preloaded_pages
                if preloaded_pages is not None and not request.metadata_filters.active
                else self.load_pages(
                    effective_identifiers,
                    include_restricted=request.include_restricted,
                )
            )
            raw_chunks = retrieve_relevant_chunks(
                request.question,
                effective_identifiers,
                limit=guard_config.candidate_pool_size if guard_config.enabled else request.top_k,
                include_restricted=request.include_restricted,
            )
            has_embeddings = documents_have_embeddings(effective_identifiers)
        elif request.scope == "full_corpus":
            pages = []
            if request.metadata_filters.active:
                raw_chunks = retrieve_relevant_chunks(
                    request.question,
                    effective_identifiers,
                    limit=request.top_k,
                    include_restricted=request.include_restricted,
                )
            else:
                raw_chunks = search_full_corpus(
                    request.question,
                    limit=request.top_k,
                    include_restricted=request.include_restricted,
                )
            # Full-corpus search is exclusively vector-backed. Empty results
            # therefore mean no vector evidence, not a page fallback.
            has_embeddings = True
        else:  # pragma: no cover - Literal protects typed callers
            raise ValueError(f"Unknown retrieval scope: {request.scope}")

        region_rows: list[dict] = []
        if request.metadata_filters.country_regions:
            region_rows = metadata_filter_service.repository.list_records(
                effective_identifiers,
                include_restricted=request.include_restricted,
            )
        if len(request.metadata_filters.country_regions) > 1:
            raw_chunks = self._supplement_region_evidence(
                request,
                raw_chunks,
                region_rows,
            )

        validation_report = {}
        plan = None
        if guard_config.enabled:
            try:
                plan, plan_telemetry = evidence_validation.plan_question(
                    request.question, guard_config
                )
                groups = []
                if request.scope == "selected" and len(plan["requirements"]) > 1:
                    for requirement in plan["requirements"]:
                        group = retrieve_relevant_chunks(
                            requirement["question"],
                            effective_identifiers,
                            limit=request.top_k,
                            include_restricted=request.include_restricted,
                        )
                        groups.append(group)
                    merged = {str(c["chunk_id"]): c for c in raw_chunks}
                    for group in groups:
                        for item in group:
                            merged[str(item["chunk_id"])] = item
                    raw_chunks = sorted(
                        merged.values(), key=lambda c: c.get("reranker_score", -1), reverse=True
                    )
                if (
                    request.scope == "selected"
                    and guard_config.per_document_quota
                    and len(effective_identifiers) > 1
                ):
                    merged = {str(c["chunk_id"]): c for c in raw_chunks}
                    for identifier in effective_identifiers[:12]:
                        for item in retrieve_relevant_chunks(
                            request.question,
                            [identifier],
                            limit=2,
                            include_restricted=request.include_restricted,
                        ):
                            merged.setdefault(str(item["chunk_id"]), item)
                    raw_chunks = sorted(
                        merged.values(), key=lambda c: c.get("reranker_score", -1), reverse=True
                    )
                raw_chunks = allocate(
                    raw_chunks,
                    request.top_k,
                    groups=groups,
                    per_document=guard_config.per_document_quota,
                )
                validation_report = {"plan": plan, "plan_telemetry": plan_telemetry}
            except BudgetExceeded:
                raise
            except Exception as exc:
                validation_report = {
                    "allowed": False,
                    "error": str(exc),
                    "reason": "Question contract failed; blocked closed.",
                }
        chunks = [chunk for chunk in raw_chunks if is_chunk_relevant(request.question, chunk)]
        context_items = chunks if has_embeddings else pages
        context, truncated = format_context(context_items)
        citations = self._citations(chunks, pages if not has_embeddings and not chunks else [])
        sufficient, reason = assess_evidence_sufficiency(
            question=request.question,
            raw_chunks=raw_chunks,
            pages=pages,
            context=context,
            has_embeddings=has_embeddings,
        )
        if guard_config.enabled:
            if plan is None:
                sufficient, reason = False, validation_report["reason"]
            elif sufficient:
                report = evidence_validation.answerability(
                    request.question, plan, chunks, guard_config
                )
                validation_report.update(report)
                sufficient, reason = report["allowed"], report.get("reason")
            else:
                validation_report.update(
                    {"allowed": False, "reason": reason, "stage": "score_gate"}
                )
        missing_regions = self._missing_requested_regions(
            request,
            chunks,
            region_rows,
        )
        if missing_regions:
            sufficient = False
            reason = (
                "No relevant evidence was retrieved for every explicitly requested "
                f"region. Missing: {', '.join(missing_regions)}."
            )
        result = RetrievalResult(
            pages=pages,
            chunks=chunks,
            raw_chunks=raw_chunks,
            citations=citations,
            context=context,
            truncated=truncated,
            used_vector_retrieval=has_embeddings,
            evidence=EvidenceDecision(sufficient, reason),
            filter_applied=filter_application.applied,
            filter_fallback=filter_application.fallback,
            filter_notice=filter_application.notice,
            validation_report=validation_report,
        )
        return result

    @staticmethod
    def _supplement_region_evidence(
        request: RetrievalRequest,
        raw_chunks: list[dict],
        region_rows: list[dict],
    ) -> list[dict]:
        """Diversify comparison retrieval across explicitly named regions."""

        merged = list(raw_chunks)
        seen = {str(chunk.get("chunk_id")) for chunk in merged}
        per_region_limit = max(2, request.top_k // len(request.metadata_filters.country_regions))
        for region in request.metadata_filters.country_regions:
            region_ids = [
                str(row["id"])
                for row in region_rows
                if str(row.get("country_region") or "").casefold() == region.casefold()
            ]
            if not region_ids:
                continue
            candidates = retrieve_relevant_chunks(
                f"{request.question}\nFocus region: {region}",
                region_ids,
                limit=per_region_limit,
                include_restricted=request.include_restricted,
            )
            for chunk in candidates:
                key = str(chunk.get("chunk_id"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(chunk)
        return merged

    @staticmethod
    def _missing_requested_regions(
        request: RetrievalRequest,
        chunks: list[dict],
        region_rows: list[dict],
    ) -> list[str]:
        if not request.metadata_filters.country_regions:
            return []
        cited_document_ids = {str(chunk.get("document_id")) for chunk in chunks}
        missing: list[str] = []
        for region in request.metadata_filters.country_regions:
            region_document_ids = {
                str(row["id"])
                for row in region_rows
                if str(row.get("country_region") or "").casefold() == region.casefold()
            }
            if not (region_document_ids & cited_document_ids):
                missing.append(region)
        return missing

    def validate_questions(self, request: QuestionValidationRequest) -> list[str]:
        """Return answerable candidates using one batched dense retrieval pass."""

        questions = [question.strip() for question in request.questions if question.strip()]
        if not questions or not request.identifiers or request.max_results <= 0:
            return []
        if request.top_k <= 0:
            raise ValueError("Question validation top_k must be greater than zero.")

        document_ids = resolve_document_ids(
            list(request.identifiers),
            request.include_restricted,
        )
        vectors = embedding.embed_queries(questions)
        if len(vectors) != len(questions):
            raise RuntimeError("Embedding provider returned an unexpected query-vector count.")

        dense_limit = max(request.top_k * 3, 20)
        result_groups = embedding_repository.retrieve_many(
            [embedding.vector_literal(vector) for vector in vectors],
            document_ids,
            limit=dense_limit,
        )
        if len(result_groups) != len(questions):
            raise RuntimeError("Batch retrieval returned an unexpected result-group count.")

        gate_distance = (
            request.max_distance if request.max_distance is not None else max_vector_distance()
        )
        distance_survivors: list[tuple[int, str, list[dict]]] = []
        for index, (question, chunks) in enumerate(zip(questions, result_groups, strict=True)):
            if not chunks:
                continue
            best_distance = min(float(chunk.get("distance", 1.0)) for chunk in chunks)
            if best_distance <= gate_distance:
                distance_survivors.append((index, question, chunks))

        if not request.use_reranker or not reranking.enabled():
            return [question for _, question, _ in distance_survivors][: request.max_results]

        # Gate candidates concurrently for both providers: onnxruntime releases
        # the GIL during inference, so the local cross-encoder also benefits —
        # a sequential per-candidate loop here was the dominant latency of
        # follow-up suggestion generation.
        passed_indices: set[int] = set()
        workers = min(3, len(distance_survivors))
        if workers:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    index: executor.submit(
                        bind(self._passes_reranker_gate),
                        question,
                        chunks,
                        request.top_k,
                    )
                    for index, question, chunks in distance_survivors
                }
                for index, future in futures.items():
                    if future.result():
                        passed_indices.add(index)

        return [question for index, question, _ in distance_survivors if index in passed_indices][
            : request.max_results
        ]

    @staticmethod
    def _passes_reranker_gate(question: str, chunks: list[dict], top_k: int) -> bool:
        try:
            ranked = reranking.rerank(question, chunks[:top_k], limit=top_k)
        except Exception:
            logger.exception("Reranker validation failed for candidate; dropping it")
            return False
        scores = [chunk["reranker_score"] for chunk in ranked if "reranker_score" in chunk]
        return bool(scores) and max(scores) >= min_reranker_score()

    @staticmethod
    def _citations(chunks: list[dict], pages: list[dict]) -> list[dict]:
        if chunks:
            return [
                {
                    "document_id": chunk["document_id"],
                    "title": chunk.get("doc_title") or chunk["file"],
                    "chunk_id": chunk["chunk_id"],
                    "page": chunk.get("page_start") or chunk.get("page"),
                    "quote": chunk.get("text", "")[:500],
                }
                for chunk in chunks
            ]
        return [
            {
                "title": page.get("title") or page["file"],
                "page": page.get("page"),
                "quote": page.get("text", "")[:300],
            }
            for page in pages
        ]


retrieval_service = RetrievalService()
