"""Dependency-free Okapi BM25 keyword retrieval with bilingual tokenizing.

Complements dense retrieval with exact-term matching (named instruments,
acronyms, section numbers, years) and is fused with the dense candidate
pool via Reciprocal Rank Fusion before reranking. Design rationale and
alternatives: docs/BM25_HYBRID_RETRIEVAL.md.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75
DEFAULT_RRF_K = 60

# CJK runs (Han + kana) are tokenized as character bigrams — the standard
# dependency-free approximation for unsegmented Chinese/Japanese text.
_CJK_RUN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]+")
# After CJK runs are removed, remaining word characters are Latin-script
# words, acronyms, and numbers (unicode-aware, so accented words survive).
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# Minimal English stopword list: only glue words that would otherwise
# dominate document frequency. Deliberately tiny — BM25's IDF already
# down-weights common terms, and aggressive stopping hurts phrase-like
# queries ("right to be forgotten").
_STOPWORDS = frozenset(
    """a an and are as at be but by for from has have in into is it its of on
    or that the their this to was were which will with""".split()
)


def enabled() -> bool:
    return os.getenv("RETRIEVAL_BM25_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def tokenize(text: str) -> list[str]:
    """Lowercased Latin/digit word tokens plus CJK character bigrams."""
    lowered = text.lower()
    tokens: list[str] = []
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    remainder = _CJK_RUN.sub(" ", lowered)
    tokens.extend(t for t in _WORD.findall(remainder) if t not in _STOPWORDS)
    return tokens


class Bm25Index:
    """Inverted-index Okapi BM25 over a fixed list of chunk rows."""

    def __init__(
        self,
        rows: list[dict],
        *,
        k1: float | None = None,
        b: float | None = None,
    ) -> None:
        self._rows = rows
        self._k1 = k1 if k1 is not None else _env_float("RETRIEVAL_BM25_K1", DEFAULT_K1)
        self._b = b if b is not None else _env_float("RETRIEVAL_BM25_B", DEFAULT_B)
        self._doc_lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for slot, row in enumerate(rows):
            counts = Counter(tokenize(str(row.get("text") or "")))
            self._doc_lengths.append(sum(counts.values()))
            for term, term_frequency in counts.items():
                self._postings.setdefault(term, []).append((slot, term_frequency))
        total_length = sum(self._doc_lengths)
        self._average_length = (total_length / len(rows)) if rows else 1.0
        row_count = len(rows)
        self._idf = {
            term: math.log(1.0 + (row_count - len(postings) + 0.5) / (len(postings) + 0.5))
            for term, postings in self._postings.items()
        }

    def __len__(self) -> int:
        return len(self._rows)

    def search(self, query: str, limit: int) -> list[tuple[dict, float]]:
        """Top-`limit` (row, score) pairs with positive BM25 scores."""
        if limit <= 0 or not self._rows:
            return []
        scores: dict[int, float] = {}
        for term in set(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf[term]
            for slot, term_frequency in postings:
                length_norm = 1.0 - self._b + self._b * (
                    self._doc_lengths[slot] / self._average_length
                )
                denominator = term_frequency + self._k1 * length_norm
                scores[slot] = scores.get(slot, 0.0) + idf * (
                    term_frequency * (self._k1 + 1.0) / denominator
                )
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [(self._rows[slot], score) for slot, score in ranked[:limit] if score > 0.0]


@dataclass
class _CacheEntry:
    fingerprint: tuple
    index: Bm25Index


class Bm25IndexCache:
    """Small LRU of per-scope indexes, validated by a corpus fingerprint.

    The fingerprint (chunk count + newest chunk timestamp for the scope) is
    fetched with one cheap SQL query per lookup; re-ingest changes it, a
    re-embed deliberately does not (BM25 is embedding-model independent).
    """

    def __init__(self, max_entries: int = 8) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(
        self,
        key: tuple,
        fingerprint: tuple,
        build: Callable[[], Bm25Index],
    ) -> Bm25Index:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.fingerprint == fingerprint:
                self._entries.move_to_end(key)
                return entry.index
        index = build()
        with self._lock:
            self._entries[key] = _CacheEntry(fingerprint=fingerprint, index=index)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return index

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_index_cache = Bm25IndexCache()


def bm25_search(
    question: str,
    *,
    document_ids: list[str] | None = None,
    include_restricted: bool = False,
    limit: int,
) -> list[dict]:
    """BM25-ranked chunk rows for the scope, in the dense-candidate shape
    plus a `bm25_score` field. Returns [] when disabled, empty, or on any
    internal failure — the sparse path must never break retrieval.
    """
    if not enabled() or limit <= 0:
        return []
    from app.modules.documents.repositories.chunk_texts import chunk_text_repository

    try:
        fingerprint = chunk_text_repository.corpus_fingerprint(
            document_ids,
            include_restricted=include_restricted,
        )
        if not fingerprint[0]:
            return []
        key = (
            tuple(sorted(str(item) for item in document_ids)) if document_ids else "*",
            include_restricted,
        )
        index = _index_cache.get(
            key,
            fingerprint,
            lambda: Bm25Index(
                chunk_text_repository.list_chunk_rows(
                    document_ids,
                    include_restricted=include_restricted,
                )
            ),
        )
        return [dict(row, bm25_score=score) for row, score in index.search(question, limit)]
    except Exception:
        logger.exception("BM25 keyword search failed; falling back to dense-only retrieval")
        return []


def rrf_merge(
    dense: list[dict],
    sparse: list[dict],
    *,
    limit: int,
    k: int | None = None,
) -> list[dict]:
    """Reciprocal Rank Fusion of the dense and BM25 candidate rankings.

    `dense` must already be ranked best-first (ascending cosine distance),
    `sparse` best-first by BM25 score. RRF needs no cross-scale score
    normalisation; a chunk found by both sources naturally rises.
    """
    rrf_k = k if k is not None else int(_env_float("RETRIEVAL_RRF_K", DEFAULT_RRF_K))
    scores: dict[str, float] = {}
    merged: dict[str, dict] = {}
    for rank, row in enumerate(dense):
        chunk_key = str(row.get("chunk_id"))
        merged[chunk_key] = row
        scores[chunk_key] = scores.get(chunk_key, 0.0) + 1.0 / (rrf_k + rank + 1)
    for rank, row in enumerate(sparse):
        chunk_key = str(row.get("chunk_id"))
        existing = merged.get(chunk_key)
        if existing is None:
            merged[chunk_key] = row
        elif "bm25_score" in row:
            merged[chunk_key] = {**existing, "bm25_score": row["bm25_score"]}
        scores[chunk_key] = scores.get(chunk_key, 0.0) + 1.0 / (rrf_k + rank + 1)
    ordered = sorted(scores.items(), key=lambda item: -item[1])
    return [merged[chunk_key] for chunk_key, _ in ordered[:limit]]
