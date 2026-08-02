from __future__ import annotations

from app.modules.documents.service import (
    documents_have_embeddings,
    read_documents,
    retrieve_relevant_chunks,
    search_full_corpus,
)
from app.modules.retrieval.contracts import (
    EvidenceDecision,
    RetrievalRequest,
    RetrievalResult,
)
from app.modules.retrieval.evidence import assess_evidence_sufficiency, is_chunk_relevant
from app.modules.retrieval.formatting import format_context


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
