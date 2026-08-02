from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.service import (
    documents_have_embeddings,
    read_documents,
    resolve_document_ids,
    retrieve_relevant_chunks,
    search_full_corpus,
)
from app.modules.embedding import service as embedding
from app.modules.reranking import service as reranking
from app.modules.retrieval.contracts import (
    EvidenceDecision,
    QuestionValidationRequest,
    RetrievalRequest,
    RetrievalResult,
)
from app.modules.retrieval.evidence import (
    assess_evidence_sufficiency,
    is_chunk_relevant,
    max_vector_distance,
    min_reranker_score,
)
from app.modules.retrieval.formatting import format_context

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
        if request.top_k <= 0:
            raise ValueError("Retrieval top_k must be greater than zero.")
        if request.scope == "selected" and not request.identifiers:
            raise ValueError("Selected-document retrieval requires at least one document.")

        identifiers = list(request.identifiers)
        if request.scope == "selected":
            pages = (
                preloaded_pages
                if preloaded_pages is not None
                else self.load_pages(
                    identifiers,
                    include_restricted=request.include_restricted,
                )
            )
            raw_chunks = retrieve_relevant_chunks(
                request.question,
                identifiers,
                limit=request.top_k,
                include_restricted=request.include_restricted,
            )
            has_embeddings = documents_have_embeddings(identifiers)
        elif request.scope == "full_corpus":
            pages = []
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

        chunks = [
            chunk
            for chunk in raw_chunks
            if is_chunk_relevant(request.question, chunk)
        ]
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
        return RetrievalResult(
            pages=pages,
            chunks=chunks,
            raw_chunks=raw_chunks,
            citations=citations,
            context=context,
            truncated=truncated,
            used_vector_retrieval=has_embeddings,
            evidence=EvidenceDecision(sufficient, reason),
        )

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
            request.max_distance
            if request.max_distance is not None
            else max_vector_distance()
        )
        distance_survivors: list[tuple[int, str, list[dict]]] = []
        for index, (question, chunks) in enumerate(
            zip(questions, result_groups, strict=True)
        ):
            if not chunks:
                continue
            best_distance = min(float(chunk.get("distance", 1.0)) for chunk in chunks)
            if best_distance <= gate_distance:
                distance_survivors.append((index, question, chunks))

        if not request.use_reranker or not reranking.enabled():
            return [question for _, question, _ in distance_survivors][
                : request.max_results
            ]

        passed_indices: set[int] = set()
        reranker_provider = reranking.active_config().provider
        if reranker_provider == "local":
            for index, question, chunks in distance_survivors:
                if self._passes_reranker_gate(question, chunks, request.top_k):
                    passed_indices.add(index)
                if len(passed_indices) >= request.max_results:
                    break
        else:
            workers = min(3, len(distance_survivors))
            if workers:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {
                        index: executor.submit(
                            self._passes_reranker_gate,
                            question,
                            chunks,
                            request.top_k,
                        )
                        for index, question, chunks in distance_survivors
                    }
                    for index, future in futures.items():
                        if future.result():
                            passed_indices.add(index)

        return [
            question
            for index, question, _ in distance_survivors
            if index in passed_indices
        ][: request.max_results]

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
