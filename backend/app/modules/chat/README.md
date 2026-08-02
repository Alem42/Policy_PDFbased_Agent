# Chat module

The Chat module turns a persisted user turn into an evidence-backed answer. HTTP, retrieval,
orchestration, generation, and persistence are separate so each capability can be called and tested
without starting FastAPI.

## Public entry points

| Capability | Import | Behaviour |
| --- | --- | --- |
| Start a persisted turn | `chat.application.turn_service.chat_turn_service` | Checks ownership, reads prior history, writes the new user message, optionally creates a pending answer row. |
| Fixed Direct answer | `chat.orchestration.direct.direct_orchestrator` | One selected-document retrieval, Evidence Gate, then answer/refusal. |
| ReAct graph | `chat.orchestration.react.react_orchestrator` | Multi-step selected/full-corpus/web search with interrupts and persistence. |
| Retrieval only | `retrieval.service.retrieval_service` | Selected or full-corpus chunks, context, citations, and Evidence Gate result. |
| Permanent web import | `documents.web_import.web_import_service` | Validates, fetches, ingests, deduplicates, and returns a ready shared document. |
| Web search/fetch | `web_search.service.web_search_service` | Provider-independent transient web access. |

## Direct example

```python
from app.modules.chat.orchestration.direct import direct_orchestrator

result = direct_orchestrator.answer(
    question="What implementation deadline does the policy set?",
    document_ids=[document_id],
    top_k=8,
    response_mode="researcher",
    answer_mode="analysis",
)
```

The orchestrator is synchronous because embedding and reranking may be CPU-bound. Async callers
should use `await asyncio.to_thread(direct_orchestrator.answer, ...)`.

## Retrieval example

```python
from app.modules.retrieval.contracts import RetrievalRequest
from app.modules.retrieval.service import retrieval_service

result = retrieval_service.retrieve(
    RetrievalRequest(
        question="What funding is provided?",
        scope="selected",
        identifiers=(document_id,),
        top_k=6,
    )
)

if result.evidence.sufficient:
    print(result.context, result.citations)
```

## Important boundaries

- Routes translate HTTP and SSE only; turn persistence belongs to `ChatTurnService`.
- Direct and ReAct call `RetrievalService`; they do not call each other's LangGraph nodes.
- Document ingestion uses `core.ai.chat_models`, never Chat generation internals.
- Web providers belong to `modules.web_search`; permanent ingestion belongs to Documents.
- Provider token usage is reported only when the provider supplies metadata; it is not estimated.

## Compatibility packages

`chat.rag.graph`, `chat.rag.agent`, and `chat.rag.web_search` remain during migration because tests
and downstream branches may still import them. New code should use the public entry points above.

## Tests

From `backend/`:

```powershell
pytest tests/test_chat_router.py tests/test_chat_rag_modes.py tests/test_agent_tools.py
pytest tests/test_chat_turn_service.py tests/test_web_import_service.py
ruff check app tests
```
