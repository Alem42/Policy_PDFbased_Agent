"""Chunk and evidence-gate transient web search results."""

import logging

from app.modules.documents.chunker import TiktokenDocumentChunker
from app.modules.embedding import service as embedding
from app.modules.reranking.service import enabled as reranker_enabled
from app.modules.reranking.service import rerank as rerank_chunks
from app.modules.retrieval.evidence import max_vector_distance, min_reranker_score
from app.modules.web_search.contracts import WebSearchResult

logger = logging.getLogger(__name__)
_chunker = TiktokenDocumentChunker()


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1 - dot / (norm_a * norm_b)


def chunk_web_result_text(text: str) -> list[str]:
    """Split fetched result content into retrieval-sized pieces."""

    clean = text.strip()
    if not clean:
        return []
    chunks = _chunker.chunk([{"page": 1, "text": clean}])
    return [chunk["text"] for chunk in chunks] or [clean]


def score_web_results(
    query: str,
    results: list[WebSearchResult],
) -> tuple[bool, str | None, list[dict]]:
    """Apply the document evidence thresholds to transient web results."""

    if not results:
        return False, "The web search returned no results.", []
    owners: list[int] = []
    texts: list[str] = []
    for index, result in enumerate(results):
        for chunk_text in chunk_web_result_text(result.content or result.title):
            owners.append(index)
            texts.append(chunk_text)
    if not texts:
        return False, "The web search returned no usable content.", []

    query_vector = embedding.embed_query(query)
    chunk_vectors = embedding.embed_documents(texts)
    best_per_result: dict[int, dict] = {}
    for owner, text, vector in zip(owners, texts, chunk_vectors, strict=True):
        distance = cosine_distance(query_vector, vector)
        current = best_per_result.get(owner)
        if current is None or distance < current["distance"]:
            best_per_result[owner] = {
                "title": results[owner].title,
                "url": results[owner].url,
                "text": text,
                "distance": distance,
                "passed": False,
            }
    candidates = [
        best_per_result[index]
        for index in range(len(results))
        if index in best_per_result
    ]
    relevant = [
        candidate
        for candidate in candidates
        if candidate["distance"] <= max_vector_distance()
    ]
    if not relevant:
        return False, "No web result was close enough to the question.", candidates

    if reranker_enabled():
        try:
            reranked = rerank_chunks(query, relevant, limit=len(relevant))
            best_score = max(
                candidate.get("reranker_score", min_reranker_score())
                for candidate in reranked
            )
            if best_score < min_reranker_score():
                return False, "No web result passed the relevance reranker.", candidates
            relevant = reranked
        except Exception:
            logger.exception("Reranking web search results failed; using cosine ranking only.")

    passed_urls = {candidate["url"] for candidate in relevant}
    for candidate in candidates:
        candidate["passed"] = candidate["url"] in passed_urls
    return True, None, candidates
