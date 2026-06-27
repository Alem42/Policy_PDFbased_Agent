# Backend Initial Project

This folder is a clean backend skeleton for the Policy in Action Library MVP.

## MVP Flow

```text
Admin uploads trusted policy documents
-> backend validates metadata and file
-> ingestion extracts text and chunks it
-> RAG module embeds and indexes chunks
-> user selects documents and asks questions
-> RAG retrieves relevant chunks
-> answer is generated with citations
```

## Module Owners

- Admin upload and metadata: `app/admin`, `app/api/routes/admin.py`
- Ingestion and chunking: `app/ingestion`
- RAG chat: `app/rag`, `app/api/routes/chat.py`
- Crawler skeleton: `app/crawlers`, `app/api/routes/crawlers.py`
- Document library: `app/api/routes/documents.py`
- Database schema: `database/init.sql`
- QA: `tests`
