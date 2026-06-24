# Policy in Action Library Backend

This is the initial backend skeleton for the Policy in Action Library project.

The goal of this folder is to provide a clean `master` baseline for modular team development. Most endpoints are placeholders returning `501 Not Implemented`; each teammate can implement one module in their own feature branch.

## MVP Modules

- Admin document management: upload, metadata editing, processing status.
- Ingestion pipeline: file validation, PDF/text extraction, chunking, indexing.
- RAG pipeline: embeddings, retrieval, answer generation, citations.
- Crawler pipeline: trusted source registration, crawl jobs, future external data collection.
- Document library: list, filter, detail, chunks.

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Run Tests

```powershell
cd backend
pytest
ruff check app tests
```

## Suggested Branches

- `feature/admin-upload`
- `feature/ingestion-pipeline`
- `feature/rag-chat`
- `feature/crawler-sources`
- `feature/document-library`
- `feature/database-schema`

Keep `master` stable. Implement features in branches and merge back regularly after tests pass.
