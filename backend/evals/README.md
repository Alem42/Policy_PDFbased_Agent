# Policy Search Evaluations

The smoke dataset exercises the framework-independent `PolicySearchCapability` rather than HTTP or LangGraph. This keeps retrieval experiments reproducible and makes the same cases reusable by a future MCP adapter.

## Prerequisites

1. PostgreSQL is running and the backend database configuration is valid.
2. Migration `028_add_agent_run_events.sql` has been applied when using an existing database volume.
3. The demo policy PDFs under `backend/data/demo_sources/` have been ingested with their original filenames.
4. Embedding and reranker models are available.

## Run

From `backend/`:

```powershell
python scripts/run_smoke_evals.py --max-concurrency 2
```

To make a failed case return a non-zero process status for CI:

```powershell
python scripts/run_smoke_evals.py --max-concurrency 2 --fail-on-regression
```

JSON and Markdown reports are written to `backend/eval-results/`. The directory is ignored because experiment outputs are environment-specific; the JSONL dataset and Runner remain version controlled.

## Current boundary

These 15 cases cover selected-document retrieval, full-library retrieval, Chinese/English queries, citation presence and an insufficient-evidence case. They do not yet evaluate answer generation, live web search, interrupt/resume or multi-step Agent strategy. Those belong in the next full-agent dataset after this retrieval baseline is stable.
