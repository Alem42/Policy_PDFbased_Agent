# Chat and Web Import Refactor Strategy

## Purpose

This document is the execution checklist and recovery point for the chat refactor. The work is
split into independently testable phases so it can continue safely if the implementation session
is interrupted or the working context is compacted.

The refactor must preserve the existing HTTP API and database schema unless a phase explicitly
documents a compatible migration. Existing Direct and ReAct behaviour remain available throughout.

## Problems being addressed

1. Web import validation differs between the admin endpoint and the Agent tool.
2. A supplied web-page title is used as a filename but is not reliably persisted as metadata.
3. URL, byte-level, normalised-text, and semantic duplicate paths return inconsistent outcomes.
4. Import has no common size/content policy, incomplete failure handling, and weak integration tests.
5. `chat/router.py` mixes HTTP routing, session lifecycle, persistence, SSE formatting, orchestration,
   usage accounting, citations, and follow-up suggestions.
6. ReAct tools call Direct LangGraph nodes instead of a reusable retrieval service.
7. Direct, ReAct, and Suggestions independently assemble overlapping retrieval operations.
8. Web search lives below `chat.rag` even though document administration also depends on it.
9. Several contracts and response types are unused or owned by the wrong module.

## Target dependency direction

```text
FastAPI routes
    -> chat application services
        -> DirectOrchestrator | ReactOrchestrator
            -> knowledge retrieval service
            -> answer generation service
            -> web search service
        -> conversation repository

document admin / React tool
    -> web import service
        -> web search service
        -> document ingestion service
```

No knowledge/document service may import a Chat implementation module. Orchestrators may depend on
shared services, but one orchestrator must not call another orchestrator's LangGraph nodes.

## Target layout

```text
app/modules/chat/
|-- api/
|   |-- router.py              # thin HTTP endpoints
|   |-- history_router.py
|   `-- sse.py                 # ChatEvent -> SSE encoding
|-- application/
|   |-- turn_service.py        # session/message lifecycle
|   `-- models.py              # internal TurnContext/TurnResult
|-- orchestration/
|   |-- direct/                # fixed retrieval/evidence/generation workflow
|   `-- react/                 # tool-calling graph and policies
|-- generation/                # answer prompts, citation formatting, LLM writer
|-- suggestions/               # follow-up question feature
`-- persistence/               # conversation/checkpoint persistence

app/modules/retrieval/
|-- contracts.py               # stable request/result/evidence models
`-- service.py                 # reusable selected/full-corpus retrieval black box

app/modules/web_search/
|-- contracts.py
|-- service.py                 # active provider facade
`-- providers/

app/modules/documents/
`-- web_import.py              # secure permanent import black box
```

The final layout may retain compatibility re-export modules temporarily. New code must use the
canonical locations.

## Public black-box interfaces

### Web import

```python
result = await web_import_service.import_page(
    WebImportRequest(url=url, title=title, imported_by=user_id, imported_via="admin")
)
```

The service owns URL validation, fetching, content limits, title overrides, ingestion, deduplication,
cleanup policy, and a stable `WebImportResult`.

### Retrieval

```python
result = retrieval_service.retrieve(
    RetrievalRequest(question=question, scope=scope, top_k=top_k, include_restricted=is_admin)
)
```

The result owns retrieved chunks, citations, formatted context, truncation, and evidence decision.
Direct, ReAct, and Suggestions call this service rather than LangGraph nodes.

### Chat turn lifecycle

```python
turn = await chat_turn_service.start(request)
await chat_turn_service.finalize_message(message_id, answer, citations)
await chat_turn_service.fail(message_id, partial_answer)
```

Routes do not issue individual session/message repository operations.

## Execution phases and completion criteria

### Phase 0 - Baseline and strategy

- [x] Record current layout and risks.
- [x] Add this strategy document.
- [x] Run focused baseline tests before behaviour changes.

### Phase 1 - Web import hardening

- [x] Introduce `documents.web_import` request/result/service.
- [x] Validate public URLs for every entry point.
- [x] Reject blank and oversized fetched content in one place.
- [x] Normalise URLs for deduplication without discarding meaningful query parameters.
- [x] Persist an administrator-supplied title as a metadata override.
- [x] Convert all duplicate layers into the same successful duplicate result.
- [x] Make processing/cleanup behaviour explicit and tested.
- [x] Keep admin and Agent APIs compatible.
- [x] Add unit/service/router tests for validation, title, duplicates, provider and processing errors.

### Phase 2 - Reusable retrieval black box

- [x] Define stable `RetrievalRequest`, `RetrievalResult`, `EvidenceDecision`, and scope types.
- [x] Move selected-document retrieval out of Direct graph nodes.
- [x] Move full-corpus retrieval behind the same service.
- [x] Update Direct and ReAct code to call the service.
- [x] Update Suggestions to reuse the applicable retrieval primitives.
- [x] Remove or replace unused `chat.rag.contracts`.

### Phase 3 - Chat application boundary

- [x] Extract SSE encoding/event mapping from `chat/router.py`.
- [x] Extract token-usage aggregation from the router.
- [x] Extract conversation/session lifecycle into `ChatTurnService`.
- [x] Move Direct/ReAct stream drivers and suggestion-tail handling out of the HTTP router.
- [x] Keep `/chat`, `/chat/stream`, and `/chat/resume` contracts unchanged.
- [x] Add service-level tests so features can be called without FastAPI.

### Phase 4 - Package and dependency cleanup

- [x] Move web-search ownership outside Chat and provide temporary compatibility imports.
- [x] Add explicit Direct and ReAct orchestration facades so their roles are obvious.
- [x] Split Agent tool policy and web evidence scoring into focused modules.
- [ ] Move duplicate schemas to their owning module.
- [x] Remove dead contracts only after global import checks.
- [x] Add package READMEs describing entry points, flows, extension points, and test commands.

### Phase 5 - Verification

- [x] Run focused tests after each phase.
- [x] Run `pytest` and fix all failures caused or exposed by this task.
- [x] Run `ruff check app tests`.
- [x] Run the frontend production build.
- [x] Exercise a real stored document with representative questions.
- [x] Exercise web import with deterministic provider/service tests, including duplicate import.
- [x] Verify Direct and ReAct output/citations against expected behaviour.
- [x] Record lower-priority findings that should be a separate task.

## Compatibility rules

1. Do not change frontend-visible SSE event names in this refactor.
2. Do not change request/response JSON without adding backward-compatible defaults.
3. Keep old import paths as thin re-exports while tests or downstream code still use them.
4. Do not combine retrieval, orchestration, and persistence in the same new service.
5. Prefer a small number of cohesive modules over one-file-per-function fragmentation.
6. Each new black box needs a docstring explaining inputs, outputs, side effects, and failure modes.

## Testing pyramid

1. Pure unit tests: URL normalisation, policies, citation and event mapping.
2. Service tests: fake provider/repositories around web import and retrieval.
3. Router tests: authentication, status mapping, and response compatibility.
4. Database integration: actual document, pages, chunks, embeddings, and duplicate cleanup.
5. User simulation: realistic file and questions through the same public service/API path.

## Recovery instructions

If work resumes with limited context:

1. Read this document completely.
2. Run `git status --short` and do not discard unrelated changes.
3. Continue from the first unchecked item in `Execution phases`.
4. Inspect the latest commits/diff before editing compatibility modules.
5. Run the focused tests for the phase before moving to the next one.
6. Update the checkboxes and the implementation notes below.

## Implementation notes

- Starting branch: `zzp/searchoptimize`.
- Baseline head: `fbc5d96`.
- Existing API tests mock most of the import pipeline; Phase 1 must add service-level coverage.
- The database defaults imported documents to `approved=true` and `access_level=public`; this remains
  unchanged for this refactor because only administrators can import, but should be reconsidered as a
  separate governance/product decision.

### Completed implementation notes

- Both import entry points now use `WebImportService`; Agent import no longer bypasses public-URL and
  blank-content validation.
- ReAct and Direct now call `RetrievalService`; ReAct no longer imports Direct LangGraph nodes.
- Retrieval combines dense distance, reranker score, and a conservative lexical backstop. This fixed
  a live false-negative caused by the configured embedding provider's cosine scale without accepting
  a high reranker score that had no query-term support.
- ReAct tool messages receive full retrieved Chunk text, while persisted/frontend citation quotes stay
  capped. A live test exposed the previous 500-character truncation hiding a deadline later in a Chunk.
- Indexed but irrelevant documents no longer produce misleading page-fallback citations. Page fallback
  remains available only for documents without embeddings.
- Streaming and non-streaming paths now read prior history before inserting the current question, so
  the current question is not sent to the model twice.
- Admin registration secret enforcement remains intentionally disabled until a real secret is
  configured; the earlier temporary enforcement change was reverted.
- Local `testdb` was missing migration 009. Migrations 009 and 010 were applied and the provider
  registry was seeded (five providers, 24 chat-model catalog entries).
- Suggestions now call `RetrievalService.validate_questions()` for batched evidence validation.
- Explicit metadata filters support exact policy-area, region, organisation, language, tag, year,
  and freshness constraints. A zero-result filter falls back to the original scope with a mandatory
  user-visible warning.
- Migrations 019/020 add canonical-URL uniqueness and permanent web-document lifecycle governance;
  both are mounted in Compose and were applied to local `testdb`.
- Final backend result: 232 passed, 5 skipped with no warnings. Route-level lazy loading reduced the
  initial frontend JS chunk from 1,149.60 kB to 491.91 kB and removed the Vite size warning.

### Recommended next task

1. Implement the scheduled web-refresh worker described in `WEB_KNOWLEDGE_GOVERNANCE.md`, including
   content-version retention, rollback, retry, and notification policy.
2. Implement Tavily before allowing it to be selected outside the disabled frontend option.
3. Move the remaining duplicate schemas to their owning modules once downstream imports are audited.
4. Add a management UI for web-governance status, review dates, and archive/reactivate actions if the
   product team wants these controls outside the API.
