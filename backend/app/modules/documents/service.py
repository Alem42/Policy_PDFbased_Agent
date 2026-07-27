from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.modules.documents.chunker import document_chunker
from app.modules.documents.embeddings import (
    embed_documents,
    embed_query,
    get_embedding_model_name,
    vector_literal,
)
from app.modules.documents.extraction import extract_document
from app.modules.documents.file_store import document_file_store
from app.modules.documents.ingestion.contextual_header import build_contextual_headers
from app.modules.documents.ingestion.language_detect import detect_language
from app.modules.documents.ingestion.metadata_extractor import generate_document_metadata
from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.repositories.helpers import row_to_metadata
from app.modules.documents.repositories.processing_jobs import processing_job_repository
from app.modules.documents.reranker import rerank_chunks

logger = logging.getLogger(__name__)


def process_document(document_id: str) -> None:
    """Orchestrate extraction, enrichment, chunking, and indexing."""
    logger.info("Processing started: document_id=%s", document_id)
    job_id = processing_job_repository.start(document_id, "ingest_pdf")
    try:
        document = document_repository.get_record(document_id)
        path = document_file_store.resolve(document["file_path"])
        pages = extract_document(
            path,
            on_ocr_start=lambda: document_repository.set_status(document_id, "ocr"),
        )
        document_content_repository.replace_pages(document_id, pages)
        document_repository.set_status(document_id, "parsed")

        try:
            metadata, model_name = generate_document_metadata(
                filename=document["original_filename"], pages=pages
            )
        except Exception as exc:
            logger.warning("Metadata generation failed, using defaults: %s", exc)
            metadata = _default_metadata(document["original_filename"], str(exc))
            model_name = None
        document_content_repository.upsert_generated_metadata(document_id, metadata, model_name)
        document_repository.set_status(document_id, "annotated")

        chunks = document_chunker.chunk(pages)
        # Contextual retrieval: prepend an LLM situating sentence to the EMBEDDING
        # input only; stored/displayed text stays original. Header kept for transparency.
        headers = build_contextual_headers(
            chunks,
            title=metadata.get("title"),
            summary=metadata.get("summary"),
            model=model_name,
        )
        embed_inputs = [
            f"{header}\n\n{chunk['text']}" if header else chunk["text"]
            for header, chunk in zip(headers, chunks)
        ]
        doc_language = metadata.get("language")
        for chunk, header in zip(chunks, headers):
            if header:
                chunk.setdefault("metadata_json", {})["context_header"] = header
            chunk["language"] = detect_language(chunk["text"]) or doc_language  # per-chunk lang
        chunk_vectors = embed_documents(embed_inputs)
        embeddings = [vector_literal(vector) for vector in chunk_vectors]
        embedding_repository.replace_document_chunks(
            document_id,
            chunks,
            embeddings,
            language=doc_language,
            embedding_model=get_embedding_model_name(),
        )
        document_repository.set_status(document_id, "ready")
        processing_job_repository.finish(
            job_id,
            details={
                "page_count": len(pages),
                "chunk_count": len(chunks),
                "metadata_model": model_name,
            },
        )
        logger.info(
            "Processing complete: document_id=%s pages=%d chunks=%d",
            document_id,
            len(pages),
            len(chunks),
        )
    except Exception as exc:
        logger.error("Processing failed: document_id=%s error=%s", document_id, exc)
        document_repository.set_status(document_id, "failed", str(exc))
        processing_job_repository.finish(job_id, status="failed", error_message=str(exc))
        raise


async def save_upload(upload: UploadFile) -> dict:
    filename = document_file_store.safe_filename(upload.filename or "")
    content = await upload.read()
    if not document_file_store.is_valid_content(filename, content):
        raise ValueError(f"{filename} does not look like a valid file of its type.")

    document_id = str(uuid4())
    path = document_file_store.save(filename, content, document_id)
    try:
        document_repository.create(
            document_id=document_id,
            original_filename=filename,
            stored_filename=path.name,
            file_path=document_file_store.relative_path(path),
            content=content,
            checksum=document_file_store.checksum(content),
            mime_type=document_file_store.mime_type_for(filename),
        )
    except Exception:
        document_file_store.delete(path)
        raise
    logger.info("Upload saved: document_id=%s filename=%s", document_id, filename)
    return row_to_metadata(document_repository.get_record(document_id))


def sync_existing_documents() -> None:
    known_paths = document_repository.known_file_paths()
    for path in document_file_store.discover():
        relative_path = document_file_store.relative_path(path)
        if relative_path in known_paths:
            continue
        content = path.read_bytes()
        if not document_file_store.is_valid_content(path.name, content):
            continue
        document_id = document_repository.create(
            document_id=str(uuid4()),
            original_filename=path.name,
            stored_filename=path.name,
            file_path=relative_path,
            content=content,
            checksum=document_file_store.checksum(content),
            mime_type=document_file_store.mime_type_for(path.name),
            upsert=True,
        )
        try:
            process_document(document_id)
        except Exception:
            continue


def rescan_library(reprocess_existing: bool = True) -> dict:
    sync_existing_documents()
    if not reprocess_existing:
        return {"rescanned": True, "reprocessed": 0}
    document_ids = document_repository.all_document_ids()
    for document_id in document_ids:
        process_document(document_id)
    return {"rescanned": True, "reprocessed": len(document_ids)}


def list_documents(
    include_restricted: bool = False,
    policy_area: str | None = None,
    country_or_region: str | None = None,
    source_organisation: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    rows = document_repository.list_records(
        include_restricted=include_restricted,
        policy_area=policy_area,
        country_or_region=country_or_region,
        source_organisation=source_organisation,
        tag=tag,
    )
    return [row_to_metadata(row) for row in rows]


def get_document(identifier: str, include_restricted: bool = True) -> dict:
    return document_repository.get_record(identifier, include_restricted=include_restricted)


def get_document_detail(identifier: str, include_restricted: bool = False) -> dict:
    return document_content_repository.get_detail_record(
        identifier,
        include_restricted=include_restricted,
    )


def get_document_chunks(identifier: str, include_restricted: bool = False) -> list[dict]:
    return document_content_repository.list_chunk_records(
        identifier,
        include_restricted=include_restricted,
    )


def resolve_document_file(identifier: str, include_restricted: bool = False) -> Path:
    document = document_repository.get_record(identifier, include_restricted=include_restricted)
    return document_file_store.resolve(document["file_path"])


def delete_document(identifier: str) -> None:
    document = document_repository.delete(identifier)
    document_file_store.delete(document_file_store.path(document["file_path"]))


def update_document_governance(
    identifier: str,
    approved: bool | None = None,
    access_level: str | None = None,
) -> dict:
    document_repository.update_governance(identifier, approved=approved, access_level=access_level)
    return document_content_repository.get_detail_record(identifier, include_restricted=True)


def update_document_metadata(identifier: str, payload: dict) -> dict:
    return document_content_repository.update_metadata(identifier, payload)


def extract_pages(identifier: str, include_restricted: bool = False) -> list[dict]:
    pages = document_content_repository.get_pages(
        identifier,
        include_restricted=include_restricted,
    )
    if pages:
        return pages
    document = document_repository.get_record(identifier, include_restricted=include_restricted)
    pages = extract_document(document_file_store.resolve(document["file_path"]))
    document_content_repository.replace_pages(str(document["id"]), pages)
    return pages


def read_documents(identifiers: list[str], include_restricted: bool = False) -> list[dict]:
    pages: list[dict] = []
    for identifier in identifiers:
        pages.extend(extract_pages(identifier, include_restricted=include_restricted))
    return pages


def documents_have_embeddings(identifiers: list[str]) -> bool:
    """Return True when at least one of the given documents has been indexed with embeddings."""
    if not identifiers:
        return False
    try:
        documents = [
            document_repository.get_record(identifier, include_restricted=True)
            for identifier in identifiers
        ]
        return embedding_repository.has_embeddings([str(doc["id"]) for doc in documents])
    except Exception:
        return False


def retrieve_relevant_chunks(
    question: str,
    identifiers: list[str],
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    documents = [
        document_repository.get_record(identifier, include_restricted=include_restricted)
        for identifier in identifiers
    ]
    query_vector = vector_literal(embed_query(question))

    candidate_limit = max(limit * 3, 20)
    candidates = embedding_repository.retrieve(
        query_vector,
        [str(document["id"]) for document in documents],
        limit=candidate_limit,
    )

    try:
        return rerank_chunks(
            question,
            candidates,
            limit=limit,
        )
    except Exception:
        logger.exception("Reranking failed; returning dense-vector ranking instead.")
        return candidates[:limit]


def copy_file_into_library(source_path: Path) -> str:
    content = source_path.read_bytes()
    document_id = str(uuid4())
    target = document_file_store.copy(source_path, document_id)
    try:
        return document_repository.create(
            document_id=document_id,
            original_filename=target.name,
            stored_filename=target.name,
            file_path=document_file_store.relative_path(target),
            content=content,
            checksum=document_file_store.checksum(content),
            mime_type=document_file_store.mime_type_for(target.name),
        )
    except Exception:
        document_file_store.delete(target)
        raise


def _default_metadata(filename: str, error: str) -> dict:
    return {
        "title": filename,
        "summary": None,
        "source_type": None,
        "source_organisation": None,
        "country_region": None,
        "language": None,
        "year": None,
        "publication_date": None,
        "policy_areas": [],
        "keywords": [],
        "stakeholders": [],
        "implementation_risks": [],
        "metadata_json": {"metadata_error": error},
    }
