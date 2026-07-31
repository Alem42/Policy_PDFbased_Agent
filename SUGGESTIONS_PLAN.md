# Follow-up Question Suggestions — Implementation Plan & Progress

> Working checkpoint so this feature can be resumed if a session runs out of tokens.
> Feature: after each answer, suggest a few next questions the user might ask.
> Approach **A** (LLM proposes candidates from answer+context) **+ D** (validate each
> candidate against the corpus with the existing evidence gate, so we never suggest a
> question the selected documents can't actually answer — the anti-hallucination guard).

Branch: `Version2.3`. Author: user only (NO Claude co-author in commits).

---

## Hard requirements (from the client)

1. Policy RAG — client hates hallucination / off-document answers. **Suggested questions
   must be answerable strictly from the selected documents.** A suggestion that would
   trigger "low evidence" must be filtered out BEFORE it is shown.
2. Low cost, but quality first. Scanning docs is considered cheap. Method: reuse the
   cheap part of retrieval (embed + pgvector distance) + the existing evidence thresholds.
3. Must handle **10+ documents** in the question pool without breaking.
4. Admin-configurable: count / quality / toggle etc. → a NEW section in the Manage hub.
5. Reserve (TODO) a user-profile feature: learn from which suggestions a user clicks to
   tailor future suggestions. Implement basic click logging + optional soft personalization.

Note: the LLM semantic judge in the evidence gate was DISABLED upstream (commit f6e20d0,
"over-rejecting on-topic"). We do NOT reintroduce an LLM judge; validation is vector-based
(distance + optional reranker), reusing `evidence.max_vector_distance()` / `min_reranker_score()`.

---

## Architecture of the current system (verified by reading code)

- SSE stream endpoint: `POST /chat/stream` in `app/modules/chat/router.py`.
  Events: `retrieving → thinking → token* → citations → done` (+ `error`). We ADD a
  `suggestions` event between `citations` and `done`.
- Retrieval (no LLM): `run_retrieval(...)` in `chat/rag/graph/workflow.py` returns state
  with `context`, `citations`, `raw_chunks`, `evidence_sufficient`, `answer_mode`.
- Generation: `chat/rag/generation.py`
  - `resolve_generation_target(model) -> (provider, model, config)`
  - `create_chat_client(provider, model) -> ChatOpenAI` (temperature=0)
  - `generate_answer_streaming(...)` async generator.
- Evidence gate: `chat/rag/evidence.py`
  - `assess_evidence_sufficiency(*, question, raw_chunks, pages, context, has_embeddings)`
  - `max_vector_distance()` (~0.45, admin-tunable), `min_reranker_score()` (provider-aware).
- Retrieval primitive: `documents/service.py :: retrieve_relevant_chunks(question,
  identifiers, limit, include_restricted)` → chunks with `distance` (+ `reranker_score`
  if reranker enabled). Handles multiple identifiers (pgvector `document_id = ANY(...)`).
  `documents_have_embeddings(identifiers)`, `embedding_repository.retrieve(query_vector, doc_ids, limit)`.
- Embedding service: `from app.modules.embedding import service as embedding`
  - `embedding.embed_query(text)`, `embedding.embed_documents([...])`, `embedding.vector_literal(vec)`,
    `embedding.active_model_id()`.
- Config pattern (mirror this): `core/settings_store.py :: SingleRowSettings(table)` — one
  jsonb row (id=1). See `reranking/{config,repository,service,router}.py`. Table columns:
  `id int PK, config jsonb, updated_at timestamptz`.
- Chat history: `chat/history_repository.py :: add_message(session_id, role, content,
  citations=None, evidence_sufficient=None, response_mode=None, answer_mode=None, model=None)`.
  `chat_messages` columns include citations_json, evidence_sufficient, response_mode,
  answer_mode, model, created_at. We ADD `suggestions_json jsonb`.
- Router registration: `app/api/router.py` (include_router). Add suggestions admin + user routers.
- Frontend:
  - `frontend/src/api.js` — `request()` wrapper; `askQuestionStream()` is a generic SSE
    generator that already yields ANY json event → a new `suggestions` event flows through
    with no change. Admin settings calls: GET/PUT patterns (see getRerankingSettings).
  - `frontend/src/pages/ChatPage.jsx` — `handleSubmit()` consumes the stream; messages carry
    `citations/evidenceSufficient/...`. We add `suggestions` handling + a chip row.
  - Manage hub: `frontend/src/pages/AdminManagementPage.jsx` has a `SECTIONS` array; each
    section is a component under `pages/manage/`. Add `SuggestionsSection.jsx` + register it.

---

## Backend design

### New subpackage `app/modules/chat/suggestions/`

- `config.py` — `SuggestionConfig(BaseModel)`:
  - `enabled: bool = True`
  - `max_suggestions: int = 3`            # how many chips to show ("数量")
  - `candidate_pool: int = 6`             # candidates the LLM proposes (validation headroom)
  - `validation_distance: float | None = None`  # None → use evidence gate's max_vector_distance();
                                                #   set stricter (< gate) for higher-quality suggestions
  - `use_reranker_validation: bool = True` # apply the secondary reranker floor to candidates
  - `validation_top_k: int = 5`            # chunks retrieved per candidate for validation
  - `temperature: float = 0.3`             # a little diversity in candidate wording
  - `max_question_chars: int = 140`        # keep suggestions short
  - `personalize: bool = False`            # user-profile soft personalization (off by default)
  - helpers: `effective_distance()` returns validation_distance or None-sentinel.
- `repository.py` — `SuggestionSettingsRepository` wrapping `SingleRowSettings("suggestion_settings")`.
- `service.py` — facade: `active_config()`, `status()`, `update_config(partial)`.
- `generator.py` — the core (Approach A + D). See below.
- `profile.py` — click logging repo + `recent_click_questions(user_id, limit)` +
  `personalization_hint(user_id)` (TODO-heavy; simple aggregation now).
- `router.py` — two routers:
  - `admin_router` (require_admin): `GET/PUT /admin/suggestions` (+ optional `/test`).
  - `user_router` (get_current_user): `POST /chat/suggestions/click` → log a click.

### generator.py — the algorithm

`generate_followup_suggestions(*, question, answer, context, response_mode, history,
identifiers, include_restricted, model, user_id=None) -> list[str]`

1. `cfg = service.active_config()`; if not `cfg.enabled` → return `[]`.
2. Build candidate prompt (Approach A):
   - Inputs: question, answer (truncated), a bounded slice of `context` (reuse the answer
     turn's context — already length-capped), response_mode, last few history turns, and
     (if `cfg.personalize` and user_id) a one-line personalization hint from `profile.py`.
   - Instruction: propose `candidate_pool` follow-up questions, **strictly answerable from
     the provided excerpts**, no outside knowledge, short, in the user's language, JSON array.
   - LLM: `resolve_generation_target(model)` + `create_chat_client(...)` with
     `temperature=cfg.temperature`. Reuse the exact chat provider/model.
3. Parse JSON tolerantly (strip ```json fences; regex fallback). Clean: strip, cap length,
   drop blanks/dupes, drop near-duplicates of history questions.
4. Validate each candidate (Approach D) — low cost, multi-file:
   - Batch-embed all candidates once: `embedding.embed_documents(candidates)`.
   - For each candidate vector: `embedding_repository.retrieve(vector_literal(vec), doc_ids,
     limit=validation_top_k)` → distance-ranked chunks.
   - Primary gate: `best_distance <= (cfg.validation_distance or max_vector_distance())`.
   - Secondary gate (if `cfg.use_reranker_validation` and reranker enabled): rerank the
     retrieved chunks for that candidate; require `best_reranker >= min_reranker_score()`.
   - Keep candidate iff it passes. (This is EXACTLY what a real answer's gate would do →
     guarantees no "low-evidence" suggestion is ever shown.)
5. Return the first `max_suggestions` that pass.
6. Error handling: any exception in generation → return `[]` (feature degrades silently,
   never blocks the answer). A candidate that fails validation is dropped (not shown).

Cost per turn: 1 LLM call + 1 batch embed + `candidate_pool` pgvector searches
(+ optional reranks). All after the answer is already streamed.

### Wiring into `chat/router.py` (stream)

- After generation completes and `evidence_sufficient` and answer produced (not a refusal),
  and `cfg.enabled`: run `generate_followup_suggestions(...)` in a thread pool with a short
  timeout (e.g. 20s). Reuse `state["context"]`, `payload`, `history`, `identifiers`.
- Emit `{"type":"suggestions","items":[...]}` BEFORE `done`.
- Persist with the assistant message via `add_message(..., suggestions=items)`.
- Timeout/error → emit `{"type":"suggestions","items":[]}` (or skip) and continue to `done`.
- Refusal path (low evidence) → no suggestions.
- Also add `suggestions: list[str]` to `ChatResponse` and the non-stream `/chat` for parity.

### Persistence + schemas

- `history_repository.add_message(..., suggestions: list[str] | None = None)` → store
  `suggestions_json`. Include in `get_session_messages` + `SessionMessage.suggestions`.
- `chat/schemas.py`: `ChatResponse.suggestions: list[str] = []`; `SessionMessage.suggestions`.

### User-profile (TODO + basic)

- Table `suggestion_clicks (id uuid, user_id uuid, session_id uuid, question text,
  created_at timestamptz)`.
- `POST /chat/suggestions/click {session_id, question}` → insert a row.
- `profile.recent_click_questions(user_id, limit)` → recent clicked question texts.
- `profile.personalization_hint(user_id)` → a one-line hint injected into the candidate
  prompt when `cfg.personalize`. TODO(profile): embed clicked questions, cluster into topic
  vectors, and bias candidate ranking by similarity to the user's topic centroid.

### Migration 006 (`006_add_suggestions.sql`) + init.sql

- `CREATE TABLE suggestion_settings (id int PK, config jsonb NOT NULL DEFAULT '{}', updated_at ...)`.
- `ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS suggestions_json jsonb NOT NULL DEFAULT '[]'`.
- `CREATE TABLE suggestion_clicks (...)`.
- Mirror all three into `backend/database/init.sql`. Mount 006 in `compose.yaml` initdb.d.

---

## Frontend design

- `ChatPage.jsx`:
  - In `handleSubmit`, handle `evt.type === "suggestions"` → set `suggestions` on the last
    assistant message.
  - Render a "Suggested follow-ups" chip row under an assistant message when
    `message.suggestions?.length`. Click → set question + `requestSubmit()` + fire
    `logSuggestionClick(sessionId, text)` (non-blocking).
  - Restore stored suggestions when loading a session (from SessionMessage.suggestions).
- `api.js`: `getSuggestionSettings()`, `saveSuggestionSettings(payload)`,
  `logSuggestionClick(sessionId, question)`.
- `pages/manage/SuggestionsSection.jsx`: form (enabled, max_suggestions, candidate_pool,
  validation_distance, use_reranker_validation, validation_top_k, temperature, personalize)
  → GET/PUT `/admin/suggestions`. Register in `AdminManagementPage.jsx` SECTIONS.

---

## Tests (`backend/tests/test_suggestions.py`)

- Config load/save defaults (SingleRowSettings).
- Generator: mock the LLM to return candidates; mock retrieval so some candidates pass and
  some fail the distance gate → assert only answerable ones survive and count ≤ max_suggestions.
- Generator returns `[]` when disabled / on LLM error (fail-open to empty).
- Multi-file: pass 10+ identifiers, assert retrieval is called with all of them.
- Run the full existing suite to check for regressions.

---

## Progress log — COMPLETE

- [x] suggestions subpackage: config, repository, service
- [x] generator.py (A + D) — `create_chat_client` gained an optional `temperature` arg
- [x] profile.py (click log + hint)
- [x] migration 006 + init.sql + compose mount (007_migration_006)
- [x] wire into chat/router.py stream + /chat + schemas + history add_message
- [x] routers registered in app/api/router.py (admin + user)
- [x] frontend: ChatPage chips (submitQuestion refactor) + api.js + SuggestionsSection + registered
- [x] DB migrate on testdb (suggestion_settings, suggestion_clicks, chat_messages.suggestions_json)
- [x] tests: backend/tests/test_suggestions.py (7 pass); full suite = 135 pass, 7 FAIL are
      PRE-EXISTING refactor drift (test_embeddings/test_chunker/test_chat_rag_modes reference
      refactored-away APIs — proven identical on stashed original code), unrelated to this feature
- [x] end-to-end: generator produced 3 validated suggestions on the real corpus (real LLM +
      retrieval); config + click-log + suggestions_json persistence round-trips verified; frontend
      `npm run build` clean

### Runtime notes
- Suggestion generation runs AFTER the answer streams, in a thread pool, 45s timeout, fail-open to
  [] (never blocks the answer). A `suggestions` SSE event is emitted only when non-empty.
- Anti-hallucination guard = every candidate re-validated with retrieve_relevant_chunks +
  distance/reranker thresholds (Approach D). Reuses the SAME gate a real question faces.
- Deployment: apply migration 006 manually to existing volumes (initdb.d only runs on fresh volumes).
