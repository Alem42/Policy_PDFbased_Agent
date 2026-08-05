# BM25 Hybrid Retrieval — Design

Status: implemented (see `app/modules/retrieval/keyword_search.py`).

## Why

Dense (embedding) retrieval is the only candidate generator today. It is
strong on paraphrase and cross-lingual matching but systematically weak on
exact lexical anchors — the things policy questions are full of:

- named instruments ("Executive Order 14110", "AI Act", "《生成式人工智能服务管理暂行办法》")
- acronyms and org names (NIST, OSTP, CAC, IMDA)
- codes, section numbers, years, figures ("Article 52", "S.3050", "2027")

A question that hinges on such a token can retrieve topically-adjacent
chunks that never contain it, which then either produces a wrong citation
or trips the evidence gate into a false "insufficient" verdict. BM25 is the
standard fix: an exact-term sparse ranking fused with the dense ranking, so
each side covers the other's blind spot. This directly serves the project
goal of making retrieval "更精确" without regressing paraphrase recall.

## Constraints discovered in the codebase

1. **Storage**: PostgreSQL + pgvector. Chunk text lives once in
   `document_chunks` (model-independent); vectors live in one table per
   embedding model. There is no tsvector/GIN/FTS anywhere today.
2. **Bilingual corpus**: chunks carry `language` (English/Chinese mixed).
   Postgres' built-in text-search parsers do not tokenize CJK — real
   Chinese FTS needs the `zhparser`/`pg_jieba` extension, i.e. a different
   Docker image for the `db` service.
3. **No BM25/lexical library** is installed (`rank_bm25`, `bm25s`, nltk…),
   and the backend passes vectors as SQL string literals via psycopg —
   there is no ORM in the retrieval path.
4. **Single retrieval funnel**: both agent search tiers and the Direct path
   call `documents/service.py::retrieve_relevant_chunks` (selected scope) or
   `search_full_corpus` (whole library). Both fetch a dense candidate pool
   of `max(limit*3, 20)` and pass it to `_rerank_or_dense`.
5. **Downstream contract**: every consumer reads `chunk["distance"]`
   (cosine distance). `is_chunk_relevant` and the evidence gate treat a
   missing distance as worst-case, so BM25-only candidates must get a real
   distance backfilled or they would be gated out despite matching.
6. **Ingestion**: `replace_document_chunks` = `DELETE FROM document_chunks
   WHERE document_id=…` + re-INSERT. Any sidecar index must either cascade
   from `document_chunks` or be invalidated by content change. The
   re-embed path does NOT touch chunks.
7. Corpus scale is capstone-sized (tens of documents, 10³–10⁴ chunks).

## Decision

**Pure-Python Okapi BM25 over `document_chunks.text`, with a bilingual
tokenizer, an in-memory index cached per scope + corpus fingerprint, fused
with the dense candidate pool via Reciprocal Rank Fusion (RRF) before the
reranker.** No new dependencies, no Docker image change, no schema change.

Why not the alternatives:

- **Postgres FTS (`tsvector` + `ts_rank_cd`)**: zero-dependency and
  index-backed, but (a) it cannot tokenize Chinese without swapping the
  `ankane/pgvector` image for one with `zhparser`, and (b) `ts_rank*` is
  not BM25 (no document-length normalisation / IDF saturation). Half the
  corpus being Chinese makes (a) disqualifying on its own.
- **ParadeDB / `pg_search`**: real BM25 in Postgres, but again a different
  database image plus an extension upgrade path — far too heavy here.
- **`rank_bm25` / `bm25s` libraries**: fine, but Okapi BM25 is ~50 lines;
  a new dependency buys nothing over owning the scoring, and `rank_bm25`
  has no CJK tokenizer anyway (that part we must write regardless).

At 10³–10⁴ chunks, scoring a query in Python is sub-millisecond-to-tens-of-
milliseconds; the in-memory index build (once per corpus change) is tens of
milliseconds. An inverted index + cache keeps repeat queries cheap.

## Architecture

```
retrieve_relevant_chunks / search_full_corpus   (documents/service.py)
    │
    ├─ dense:  embedding_repository.retrieve/retrieve_all  → top-N by cosine
    ├─ sparse: keyword_search.bm25_search(scope)            → top-N by BM25
    │            └─ ChunkTextRepository.list_chunk_rows(...)  (SQL, cached)
    ├─ fuse:   rrf_merge(dense, sparse, k=60)               → top-N united
    ├─ backfill: embedding_repository.distances_for_chunks  (BM25-only rows)
    └─ _rerank_or_dense(question, fused, limit)             (unchanged)
```

### 1. Tokenizer (`keyword_search.tokenize`)

- Lowercase; extract runs of `[a-z0-9]+` as Latin/digit tokens (covers
  acronyms, years, section numbers).
- CJK codepoints are emitted as **character bigrams** (plus the lone char
  for a single-character run). Bigrams are the standard dependency-free
  approximation for Chinese segmentation and behave well with BM25.
- Mixed text yields both streams; no stopword list for CJK, a minimal
  English stopword set reused from `retrieval/evidence.py`'s spirit (kept
  local to avoid coupling).

### 2. Index (`keyword_search.Bm25Index`)

- Built from rows `{chunk_id, text, …metadata for the result shape}`.
- Inverted index `term -> [(doc_slot, term_freq)]`, per-doc lengths,
  IDF via the standard BM25 formula, `k1=1.5`, `b=0.75`.
- `search(query, limit)` returns `(row, score)` pairs, positive scores only.

### 3. Cache + invalidation (`keyword_search.Bm25IndexCache`)

- Key: `(scope_key, include_restricted)` where `scope_key` is the sorted
  tuple of document ids ("*" for full corpus).
- Validity: a **corpus fingerprint** `(chunk_count, max(created_at))`
  fetched with one cheap SQL query per lookup. Re-ingest deletes and
  re-inserts chunks, changing both; re-embed touches neither (correct —
  BM25 is embedding-model independent).
- Small LRU (a handful of scopes); full-corpus and per-conversation
  selections dominate in practice.

### 4. Candidate source (`ChunkTextRepository`)

New read-only repository (`documents/repositories/chunk_texts.py`) that
returns BM25 rows in the **same shape** dense candidates have
(`chunk_id, document_id, file, doc_title, page_start, page_end, text,
token_count, language`) so fusion and everything downstream is
shape-transparent. Visibility rules mirror `retrieve_all`
(`approved AND access_level='public'` unless `include_restricted`).

### 5. Fusion (`keyword_search.rrf_merge`)

Reciprocal Rank Fusion with the conventional `k=60`:

```
rrf(chunk) = Σ_source 1 / (k + rank_source(chunk))
```

- Sources: dense ranking (by ascending cosine distance) and BM25 ranking
  (by descending score). RRF needs no score normalisation across the two
  incomparable scales, is order-stable, and is the empirically boring-and-
  good choice for two-source hybrid retrieval.
- Output: union of both pools, sorted by RRF, truncated to the same
  `candidate_limit` the dense-only path used.

### 6. Distance backfill

BM25-only candidates carry no `distance`. One extra SQL call —
`embedding_repository.distances_for_chunks(query_vector, chunk_ids)` —
computes real cosine distances for just those chunks. Chunks with no
vector in the active model's table (not yet embedded) keep distance 1.0
(worst), so the evidence gate stays honest about them. This keeps
`is_chunk_relevant`, `assess_evidence_sufficiency`, dedup (L3) and the
suggestion validator working unchanged.

### 7. Configuration

Module constants in `keyword_search.py`, overridable by environment:

- `RETRIEVAL_BM25_ENABLED` (default `true`) — kill switch.
- `RETRIEVAL_BM25_K1` / `RETRIEVAL_BM25_B` / `RETRIEVAL_RRF_K` — tuning.

A failure anywhere in the sparse path (SQL, tokenizer, cache) logs and
falls back to dense-only candidates — BM25 must never break retrieval.

## Deliberate non-goals

- `retrieve_many` (follow-up-suggestion validation) stays dense-only: it
  validates LLM-written candidate questions, where lexical anchoring adds
  little and per-question BM25 would multiply latency.
- Web-search evidence scoring (`web_evidence.py`) stays dense-only for the
  same reason: transient content, no index to reuse.
- The dead `document_chunks.keywords text[]` column stays unused; BM25
  over full text subsumes it.
- No ANN-style index for BM25; corpus scale doesn't justify it.

## Test plan

- `tests/test_keyword_search.py`:
  - tokenizer: Latin words, acronyms/years, pure-CJK bigrams, mixed text;
  - BM25 ranking: exact-term chunk beats unrelated chunk; length
    normalisation sanity; empty query/corpus safety;
  - RRF: chunk present in both rankings outranks single-source chunks at
    similar ranks; `k` monotonicity; truncation;
  - cache: fingerprint change rebuilds, same fingerprint reuses.
- `tests/test_document_search.py` (extended): hybrid path returns BM25-only
  chunks with backfilled distance; kill switch restores dense-only
  behaviour; sparse-path failure falls back to dense.
- Manual A/B via `scripts/evaluate_retrieval_recall.py`, whose cases were
  built with `lexical_distractor` fields for exactly this dense-vs-lexical
  trade-off.
