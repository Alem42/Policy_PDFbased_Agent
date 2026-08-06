"""RAG retrieval: rank a document's (or the whole corpus's) chunks against a question.

Black box: given a question and a scope (selected documents, or the full
corpus), return the best-matching chunks, dense-ranked and optionally
BM25-fused and reranked. Used by the agent's search tools and the Direct
answer path via `app.modules.retrieval.service`. Depends on `library.py`
for identifier resolution; owns no document CRUD or ingestion.
"""

from __future__ import annotations

import logging

from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.embedding import service as embedding
from app.modules.reranking.service import enabled as reranker_enabled
from app.modules.reranking.service import rerank as rerank_chunks
from app.modules.retrieval import keyword_search

from . import library

logger = logging.getLogger(__name__)


def _rerank_or_dense(question: str, candidates: list[dict], limit: int) -> list[dict]:
    """Apply the admin-toggleable reranker to vector candidates, or fall back
    to dense-vector ranking when reranking is off or fails."""
    if not reranker_enabled():
        return candidates[:limit]
    try:
        return rerank_chunks(question, candidates, limit=limit)
    except Exception:
        logger.exception("Reranking failed; returning dense-vector ranking instead.")
        return candidates[:limit]


def _hybrid_candidates(
    question: str,
    dense: list[dict],
    *,
    query_vector: str,
    candidate_limit: int,
    document_ids: list[str] | None = None,
    include_restricted: bool = False,
) -> list[dict]:
    """Fuse BM25 keyword candidates into the dense pool via RRF.

    Only runs when dense retrieval produced candidates: an empty dense pool
    means the active model has no vectors for this scope, and the caller's
    page-fallback semantics must be preserved. BM25-only rows get a real
    cosine distance backfilled (worst-case 1.0 when the chunk has no vector)
    so every downstream distance gate keeps its meaning.
    """
    if not dense:
        return dense
    sparse = keyword_search.bm25_search(
        question,
        document_ids=document_ids,
        include_restricted=include_restricted,
        limit=candidate_limit,
    )
    if not sparse:
        return dense
    fused = keyword_search.rrf_merge(dense, sparse, limit=candidate_limit)
    missing = [c["chunk_id"] for c in fused if "distance" not in c]
    if missing:
        distances = embedding_repository.distances_for_chunks(query_vector, missing)
        for candidate in fused:
            if "distance" not in candidate:
                candidate["distance"] = distances.get(str(candidate["chunk_id"]), 1.0)
    return fused


def retrieve_relevant_chunks(
    question: str,
    identifiers: list[str],
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    document_ids = library.resolve_document_ids(identifiers, include_restricted)
    query_vector = embedding.vector_literal(embedding.embed_query(question))

    candidate_limit = max(limit * 3, 20)
    candidates = embedding_repository.retrieve(
        query_vector,
        document_ids,
        limit=candidate_limit,
    )
    candidates = _hybrid_candidates(
        question,
        candidates,
        query_vector=query_vector,
        candidate_limit=candidate_limit,
        document_ids=document_ids,
        include_restricted=include_restricted,
    )
    return _rerank_or_dense(question, candidates, limit)


def search_full_corpus(
    question: str,
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    """Hybrid (vector + BM25) search across the ENTIRE indexed corpus.

    Used by the agent's search_full_corpus tool when the caller's selected
    documents don't have enough evidence to answer from.
    """
    query_vector = embedding.vector_literal(embedding.embed_query(question))
    candidate_limit = max(limit * 3, 20)
    candidates = embedding_repository.retrieve_all(
        query_vector,
        limit=candidate_limit,
        include_restricted=include_restricted,
    )
    candidates = _hybrid_candidates(
        question,
        candidates,
        query_vector=query_vector,
        candidate_limit=candidate_limit,
        include_restricted=include_restricted,
    )
    return _rerank_or_dense(question, candidates, limit)
