# Suggested Follow-ups Optimization Checklist

This document is the implementation hand-off for optimizing validated follow-up
questions. It is intentionally explicit so another AI agent or developer can
resume the work without reconstructing the architecture.

## Goals

- Keep the main grounded answer responsive even when suggestions are slow.
- Preserve the anti-hallucination rule: only suggestions supported by the same
  selected documents may be shown.
- Replace per-candidate embedding and database setup with batch operations.
- Avoid reranking candidates that already fail the cheaper vector-distance gate.
- Keep query and passage embedding modes correct for asymmetric local models.
- Preserve suggestion order, history persistence, multi-document access control,
  fail-safe behavior, and existing admin controls.

## Guardrails

- Never call `embed_documents()` for candidate questions on an asymmetric model.
  Candidate questions require query-mode embeddings.
- Resolve document identifiers with the requesting user's `include_restricted`
  permission before retrieval.
- A suggestion failure must not remove or fail the main answer.
- Do not show unvalidated LLM output.
- Preserve unrelated working-tree changes.
- Existing PostgreSQL volumes do not rerun `docker-entrypoint-initdb.d`; migrations
  for an existing volume must be applied manually.

## Implementation sequence

### 1. Docker migration ordering

- [x] Give `006_add_embedding_settings.sql` and `006_add_suggestions.sql` unique
  container targets.
- [x] Preserve deterministic ordering with `07a_...` and `07b_...`.
- [x] Verify both bind mounts survive `docker compose config`.

### 2. Admin explanation

- [x] Expand the `Creativity (temperature)` help text.
- [x] Explain what low, medium, and high values do.
- [x] Explain that temperature affects variety, not evidence quality.
- [x] Explain that higher values can create more candidates that validation drops.

### 3. Answer-complete lifecycle

- [x] Persist the assistant answer before suggestion generation.
- [x] Emit citations immediately after answer generation.
- [x] Emit `answer_done` before the suggestion task starts.
- [x] Mark the frontend answer as non-streaming on `answer_done`.
- [x] Show a suggestion-specific loading state instead of making the answer appear
  to still be generating.
- [x] Update the persisted assistant message after suggestions are ready.
- [x] Keep the terminal `done` event for stream cleanup.

### 4. Batch query embeddings

- [x] Add `embed_queries(texts)` to the provider contract.
- [x] Implement local query batching with `query_embed(texts)`.
- [x] Implement API query batching with one `/embeddings` request.
- [x] Expose the method from `embedding.service`.
- [x] Keep `embed_query(text)` as a one-item compatibility wrapper.
- [x] Add tests proving query mode is used and output order is preserved.

### 5. Resolve documents once

- [x] Add a reusable identifier-to-document-ID resolver.
- [x] Resolve all selected documents once per suggestion validation run.
- [x] Reuse resolved IDs for every candidate.
- [x] Test that 10+ identifiers are all forwarded and resolved once.

### 6. Batch dense retrieval

- [x] Add `EmbeddingRepository.retrieve_many`.
- [x] Accept multiple query vectors and return one ordered chunk list per query.
- [x] Use one connection and one SQL round trip.
- [x] Preserve the per-query top-k limit and selected-document filter.
- [x] Keep the existing single-query retrieval API unchanged for normal RAG.
- [x] Add repository-oriented tests or mock-level contract tests.

### 7. Progressive evidence validation

- [x] Batch-embed all cleaned candidates.
- [x] Batch-retrieve dense candidates.
- [x] Apply the vector-distance gate before reranking.
- [x] Rerank only distance-passing candidates.
- [x] Rerank only the configured `validation_top_k` closest chunks rather than the
  20-chunk dense candidate pool used by normal answer retrieval.
- [x] If reranker validation is requested and an enabled reranker fails, drop that
  candidate while leaving the answer unaffected.
- [x] Preserve original candidate order in the final output.

### 8. Candidate pool and generation cost

- [x] Reduce the default candidate pool from six to five for a target of three.
- [x] Keep the admin override, because different corpora have different rejection
  rates.
- [x] Constrain the candidate LLM response to JSON and a small output budget where
  provider compatibility permits.
- [x] Document that pass-rate-driven adaptive pool sizing needs production
  telemetry and is not safe to guess from unit tests alone.

### 9. Verification

- [x] Unit-test disabled mode, generation failure, distance rejection, reranker
  rejection, deduplication, multi-file resolution, ordering, and stricter override.
- [x] Test assistant-message suggestion updates.
- [x] Test SSE event order: citations, `answer_done`, suggestions, `done`.
- [x] Run the focused suggestion and retrieval tests.
- [x] Run the full backend suite and separate pre-existing failures from regressions.
- [x] Run the frontend production build.
- [x] Run `docker compose config` and `git diff --check`.

## Verification result

- Focused suggestion/retrieval tests: `14 passed`.
- Full backend suite: `142 passed, 5 skipped`.
- Frontend: production Vite build succeeded. The existing bundle-size warning
  remains (`index` JavaScript is greater than 500 kB) and is unrelated to this
  suggestion optimization.
- Docker Compose: configuration parsed successfully and contains both unique
  migration 006 mounts.
- Git: `git diff --check` passed.

## Expected optimized request shape

Before:

```text
1 candidate LLM call
+ up to 6 query-embedding calls
+ up to 6 document-resolution passes
+ up to 6 vector-search connections
+ up to 6 reranker calls over as many as 20 chunks each
```

After:

```text
1 candidate LLM call
+ 1 batched query-embedding call
+ 1 document-resolution pass
+ 1 batched vector-search round trip
+ reranking only for distance-passing candidates, over validation_top_k chunks
```
