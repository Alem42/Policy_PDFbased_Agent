"""Snap free-form LLM policy-area labels onto canonical taxonomy leaves.

Primary normalisation path (方案①): embed the LLM output and each canonical
leaf label with the SAME embedding model, then take the nearest leaf by cosine
similarity. This tolerates wording drift ("AI Governance" -> "National AI
Strategy") that the old exact-match matcher silently dropped.

Portability: all embedding goes through embeddings.embed_documents, so swapping
the model / moving to an API only touches that module. Vectors are cached per
(model_name, label-set) — a model or taxonomy change lands on a fresh key, so we
never compare vectors produced by different models (the local-hashing-v1 trap).
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from app.modules.documents.ingestion.taxonomy import normalise_policy_areas
from app.modules.embedding import service as embedding

logger = logging.getLogger(__name__)

# Minimum cosine similarity to accept a nearest leaf. LLM output already picks
# from the taxonomy, so true matches score high (~0.8+); this floor just rejects
# unrelated hallucinations. Tune if the model changes.
MIN_MATCH_SIMILARITY = 0.5

# Keep the document tag count in the same 3-6 band the prompt asks for.
MAX_POLICY_AREAS = 6


@lru_cache(maxsize=8)
def _embed_labels(model_name: str, labels: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
    """Cache leaf-label vectors per (model, label-set).

    model_name is the active embedding model — keying on it means a model switch
    lands on a fresh entry, so we never compare label vectors from one model
    against document vectors from another (the local-hashing-v1 trap).
    """
    vectors = embedding.embed_documents(list(labels))
    return tuple(tuple(v) for v in vectors)


def _cosine(a: tuple[float, ...] | list[float], b: tuple[float, ...] | list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def match_policy_areas(values: list[str], leaf_labels: list[str]) -> list[str]:
    """Map raw labels to canonical leaves via nearest-neighbour embedding match.

    Falls back to exact matching (then ["Other"]) if embeddings are unavailable.
    """
    cleaned = [v.strip() for v in values if v and v.strip()]
    if not cleaned or not leaf_labels:
        return normalise_policy_areas(values, leaf_labels or None)

    try:
        model_name = embedding.active_model_id()
        label_vectors = _embed_labels(model_name, tuple(leaf_labels))
        value_vectors = embedding.embed_documents(cleaned)
    except Exception as exc:
        logger.warning("Embedding match unavailable, using exact match: %s", exc)
        return normalise_policy_areas(values, leaf_labels)

    matched: list[str] = []
    for vector in value_vectors:
        best_label, best_score = None, -1.0
        for label, label_vector in zip(leaf_labels, label_vectors, strict=True):
            score = _cosine(vector, label_vector)
            if score > best_score:
                best_label, best_score = label, score
        if best_label and best_score >= MIN_MATCH_SIMILARITY and best_label not in matched:
            matched.append(best_label)

    if not matched:
        return normalise_policy_areas(values, leaf_labels)
    return matched[:MAX_POLICY_AREAS]
