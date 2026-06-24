# Module Backlog

## Admin Upload

- Upload PDF/text file.
- Save metadata.
- Create document processing status.
- Edit metadata.
- Archive/delete document.

## Ingestion Pipeline

- Extract PDF text.
- Preserve page numbers.
- Clean text.
- Split into chunks.
- Store chunks.

## RAG Chat

- Generate embeddings.
- Retrieve chunks by document scope and metadata.
- Generate answer.
- Return citations.
- Refuse unsupported answers.

## Crawler Skeleton

- Register trusted sources.
- Create crawl jobs.
- Discover candidate document URLs.
- Hand discovered documents to ingestion pipeline.

## Document Library

- List documents.
- Filter by policy area, country, source, tag, year.
- Document detail page support.
- Chunk preview support.
