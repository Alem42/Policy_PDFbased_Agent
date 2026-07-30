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

- [ ] Expand the `Creativity (temperature)` help text.
- [ ] Explain what low, medium, and high values do.
- [ ] Explain that temperature affects variety, not evidence quality.
- [ ] Explain that higher values can create more candidates that validation drops.

### 3. Answer-complete lifecycle

- [ ] Persist the assistant answer before suggestion generation.
- [ ] Emit citations immediately after answer generation.
- [ ] Emit `answer_done` before the suggestion task starts.
- [ ] Mark the frontend answer as non-streaming on `answer_done`.
- [ ] Show a suggestion-specific loading state instead of making the answer appear
  to still be generating.
- [ ] Update the persisted assistant message after suggestions are ready.
- [ ] Keep the terminal `done` event for stream cleanup.

### 4. Batch query embeddings

- [ ] Add `embed_queries(texts)` to the provider contract.
- [ ] Implement local query batching with `query_embed(texts)`.
- [ ] Implement API query batching with one `/embeddings` request.
- [ ] Expose the method from `embedding.service`.
- [ ] Keep `embed_query(text)` as a one-item compatibility wrapper.
- [ ] Add tests proving query mode is used and output order is preserved.

### 5. Resolve documents once

- [ ] Add a reusable identifier-to-document-ID resolver.
- [ ] Resolve all selected documents once per suggestion validation run.
- [ ] Reuse resolved IDs for every candidate.
- [ ] Test that 10+ identifiers are all forwarded and resolved once.

### 6. Batch dense retrieval

- [ ] Add `EmbeddingRepository.retrieve_many`.
- [ ] Accept multiple query vectors and return one ordered chunk list per query.
- [ ] Use one connection and one SQL round trip.
- [ ] Preserve the per-query top-k limit and selected-document filter.
- [ ] Keep the existing single-query retrieval API unchanged for normal RAG.
- [ ] Add repository-oriented tests or mock-level contract tests.

### 7. Progressive evidence validation

- [ ] Batch-embed all cleaned candidates.
- [ ] Batch-retrieve dense candidates.
- [ ] Apply the vector-distance gate before reranking.
- [ ] Rerank only distance-passing candidates.
- [ ] Rerank only the configured `validation_top_k` closest chunks rather than the
  20-chunk dense candidate pool used by normal answer retrieval.
- [ ] If reranker validation is requested and an enabled reranker fails, drop that
  candidate while leaving the answer unaffected.
- [ ] Preserve original candidate order in the final output.

### 8. Candidate pool and generation cost

- [ ] Reduce the default candidate pool from six to five for a target of three.
- [ ] Keep the admin override, because different corpora have different rejection
  rates.
- [ ] Constrain the candidate LLM response to JSON and a small output budget where
  provider compatibility permits.
- [ ] Document that pass-rate-driven adaptive pool sizing needs production
  telemetry and is not safe to guess from unit tests alone.

### 9. Verification

- [ ] Unit-test disabled mode, generation failure, distance rejection, reranker
  rejection, deduplication, multi-file resolution, ordering, and stricter override.
- [ ] Test assistant-message suggestion updates.
- [ ] Test SSE event order: citations, `answer_done`, suggestions, `done`.
- [ ] Run the focused suggestion and retrieval tests.
- [ ] Run the full backend suite and separate pre-existing failures from regressions.
- [ ] Run the frontend production build.
- [ ] Run `docker compose config` and `git diff --check`.

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

