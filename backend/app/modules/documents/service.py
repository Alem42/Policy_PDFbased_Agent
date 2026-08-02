from __future__ import annotations

import asyncio
import io
import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.modules.documents.chunker import document_chunker
from app.modules.documents.exceptions import DuplicateDocumentError
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
from app.modules.embedding import service as embedding
from app.modules.reranking.service import enabled as reranker_enabled
from app.modules.reranking.service import rerank as rerank_chunks

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
        # L2 dedup support: hash of the normalised extracted text, distinct from
        # the L1 sha256 (exact bytes) — catches re-saved/reformatted copies.
        extracted_text = "\n".join(page.get("text") or "" for page in pages)
        if extracted_text.strip():
            document_repository.set_content_hash(
                document_id, document_file_store.normalized_content_hash(extracted_text)
            )

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

        # Admin-tunable chunk size (Manage > Embedding). Clamped to a sane ceiling;
        # if it exceeds the model's input limit, the model truncates/errs per chunk.
        chunk_budget = min(max(embedding.active_config().chunk_token_budget, 64), 8000)
        chunks = document_chunker.chunk(pages, max_tokens=chunk_budget)
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
            for header, chunk in zip(headers, chunks, strict=True)
        ]
        doc_language = metadata.get("language")
        for chunk, header in zip(chunks, headers, strict=True):
            if header:
                chunk.setdefault("metadata_json", {})["context_header"] = header
            chunk["language"] = detect_language(chunk["text"]) or doc_language  # per-chunk lang
        chunk_vectors = embedding.embed_documents(embed_inputs)
        embeddings = [embedding.vector_literal(vector) for vector in chunk_vectors]
        embedding_repository.replace_document_chunks(
            document_id,
            chunks,
            embeddings,
            language=doc_language,
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


async def save_upload(
    upload: UploadFile,
    *,
    source_url: str | None = None,
    imported_by: str | None = None,
    imported_via: str | None = None,
) -> dict:
    filename = document_file_store.safe_filename(upload.filename or "")
    content = await upload.read()
    if not document_file_store.is_valid_content(filename, content):
        raise ValueError(f"{filename} does not look like a valid file of its type.")

    checksum = document_file_store.checksum(content)
    # L1 exact-duplicate guard: identical bytes -> identical SHA-256. Check before
    # writing to disk so a duplicate never touches the filesystem or the DB.
    # L2 (normalised-text hash) and L3 (embedding similarity) dedup run in
    # save_web_import(), after extraction/embedding produce something to
    # compare — see process_document()'s content_hash step and
    # _find_near_duplicate() below.
    existing = document_repository.find_by_checksum(checksum)
    if existing:
        raise DuplicateDocumentError(str(existing["id"]), existing["original_filename"])

    document_id = str(uuid4())
    path = document_file_store.save(filename, content, document_id)
    try:
        document_repository.create(
            document_id=document_id,
            original_filename=filename,
            stored_filename=path.name,
            file_path=document_file_store.relative_path(path),
            content=content,
            checksum=checksum,
            mime_type=document_file_store.mime_type_for(filename),
            source_url=source_url,
            imported_by=imported_by,
            imported_via=imported_via,
        )
    except Exception:
        document_file_store.delete(path)
        raise
    logger.info("Upload saved: document_id=%s filename=%s", document_id, filename)
    return row_to_metadata(document_repository.get_record(document_id))


# Cosine-distance cutoff for L3 near-duplicate detection. pgvector's `<=>`
# operator returns cosine DISTANCE (0 = identical); >0.95 cosine SIMILARITY
# corresponds to <=0.05 distance.
L3_NEAR_DUPLICATE_DISTANCE = 0.05


def _slugify_filename(title: str, url: str) -> str:
    base = re.sub(r"[^\w\- ]+", "", title or "").strip().replace(" ", "_")[:80]
    if not base:
        base = document_file_store.checksum(url.encode("utf-8"))[:16]
    return f"{base}.md"


def _semantic_samples(text: str) -> list[str]:
    """Return independent regions used for conservative semantic dedup.

    Requiring agreement across multiple regions avoids deleting a document
    merely because its introduction or boilerplate resembles another chunk.
    Short pages rely on exact URL/byte/normalised-text dedup instead.
    """
    text = text.strip()
    if len(text) < 1200:
        return []
    window = min(2000, max(600, len(text) // 4))
    starts = (0, max(0, (len(text) - window) // 2), max(0, len(text) - window))
    return list(dict.fromkeys(text[start : start + window] for start in starts))


def _find_near_duplicate(document_id: str, text: str) -> dict | None:
    """Return a semantic duplicate only when all page regions agree.

    L3 is deliberately conservative. Exact duplicates are already handled by
    L1/L2; false negatives here are safer than deleting a distinct policy page.
    """
    samples = _semantic_samples(text)
    if len(samples) < 2:
        return None

    matches: list[dict[str, float]] = []
    for sample in samples:
        query_vector = embedding.vector_literal(embedding.embed_query(sample))
        candidates = embedding_repository.retrieve_all(
            query_vector,
            limit=8,
            include_restricted=True,
        )
        matches.append(
            {
                candidate["document_id"]: candidate["distance"]
                for candidate in candidates
                if candidate["document_id"] != document_id
                and candidate["distance"] <= L3_NEAR_DUPLICATE_DISTANCE
            }
        )

    common_ids = set(matches[0]).intersection(*(set(item) for item in matches[1:]))
    if not common_ids:
        return None
    closest_id = min(
        common_ids,
        key=lambda candidate_id: sum(item[candidate_id] for item in matches),
    )
    return document_repository.get_record(closest_id, include_restricted=True)


async def save_web_import(
    *,
    url: str,
    title: str,
    markdown: str,
    imported_by: str,
    imported_via: str = "web_search",
) -> tuple[dict, bool]:
    """Import a fetched web page as a citable document.

    Reuses save_upload()/process_document() unchanged: the page content is
    wrapped as a synthetic .md UploadFile so it goes through the exact same
    extraction/chunk/embed pipeline as a real upload.

    Returns (document_metadata, was_duplicate). Two dedup layers run before a
    new document is kept:
      (a) exact source_url match -> reuse the existing document immediately.
      (b) after processing: normalised-content-hash (L2), then embedding
          cosine-similarity >0.95 (L3) against the rest of the corpus ->
          reuse the existing document, discard the new one.
    """
    existing_by_url = document_repository.find_by_source_url(url)
    if existing_by_url:
        return (
            document_content_repository.get_detail_record(
                existing_by_url["id"], include_restricted=True
            ),
            True,
        )

    filename = _slugify_filename(title, url)
    upload = UploadFile(filename=filename, file=io.BytesIO(markdown.encode("utf-8")))
    try:
        saved = await save_upload(
            upload,
            source_url=url,
            imported_by=imported_by,
            imported_via=imported_via,
        )
    except DuplicateDocumentError as exc:
        # A different URL may produce byte-identical Markdown. Treat the L1
        # collision exactly like every other duplicate layer.
        return (
            document_content_repository.get_detail_record(
                exc.existing_id,
                include_restricted=True,
            ),
            True,
        )
    document_id = saved["id"]

    try:
        await asyncio.to_thread(process_document, document_id)
        duplicate = await asyncio.to_thread(
            document_repository.find_by_content_hash,
            document_file_store.normalized_content_hash(markdown),
            exclude_id=document_id,
        )
        if duplicate is None:
            duplicate = await asyncio.to_thread(_find_near_duplicate, document_id, markdown)

        if duplicate is not None:
            await asyncio.to_thread(delete_document, document_id)
            return (
                document_content_repository.get_detail_record(
                    duplicate["id"], include_restricted=True
                ),
                True,
            )

        # The fetched/site title is an explicit source fact. Persist it after
        # generated metadata so the LLM cannot silently replace the requested
        # display title.
        return document_content_repository.update_metadata(
            document_id,
            {"title": title},
        ), False
    except Exception:
        # Web import is transactional from the caller's perspective. The
        # regular upload workflow keeps failed rows for status inspection, but
        # this synchronous operation has no useful document id to return.
        try:
            await asyncio.to_thread(delete_document, document_id)
        except Exception:
            logger.exception("Failed to clean up web import %s", document_id)
        raise


def sync_existing_documents() -> None:
    known_paths = document_repository.known_file_paths()
    for path in document_file_store.discover():
        relative_path = document_file_store.relative_path(path)
        if relative_path in known_paths:
            continue
        content = path.read_bytes()
        if not document_file_store.is_valid_content(path.name, content):
            continue
        # Skip files whose content already lives in the library under another path (L1).
        if document_repository.find_by_checksum(document_file_store.checksum(content)):
            continue
        try:
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
        except DuplicateDocumentError:
            continue
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


def reembed_document(document_id: str) -> int:
    """Embed a document's EXISTING chunks into the active model's vector table.

    Reuses the stored chunks + contextual headers (no re-extract, no re-chunk),
    so other models' vectors are untouched. Used after switching embedding model
    to populate the new model's table.
    """
    rows = embedding_repository.chunks_for_reembed(document_id)
    if not rows:
        return 0
    inputs = [
        f"{row['context_header']}\n\n{row['text']}" if row.get("context_header") else row["text"]
        for row in rows
    ]
    literals = [embedding.vector_literal(vector) for vector in embedding.embed_documents(inputs)]
    embedding_repository.store_vectors([row["chunk_id"] for row in rows], literals)
    return len(rows)


def reembed_library() -> dict:
    """Re-embed every document's existing chunks for the active model."""
    document_ids = document_repository.all_document_ids()
    chunk_total = 0
    for document_id in document_ids:
        try:
            chunk_total += reembed_document(document_id)
        except Exception:
            logger.exception("Re-embed failed for document %s", document_id)
    return {
        "documents": len(document_ids),
        "chunks": chunk_total,
        "model": embedding.active_model_id(),
    }


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


def _rerank_or_dense(question: str, candidates: list[dict], limit: int) -> list[dict]:
    """Apply the admin-toggleable reranker to vector candidates, or fall back
    to dense-vector ranking when reranking is off or fails."""
    if not reranker_enabled():
        return candidates[:limit]
    try:
        return rerank_chunks(question, candidates, limit=limit)
    except Exception:
        logger.exception("Reranking failed; returning dense-vector ranking instead.")
        return candidates[:limit]


def resolve_document_ids(
    identifiers: list[str],
    include_restricted: bool = False,
) -> list[str]:
    """Resolve filenames/UUIDs once while enforcing the caller's access level."""
    return [
        str(
            document_repository.get_record(
                identifier,
                include_restricted=include_restricted,
            )["id"]
        )
        for identifier in identifiers
    ]


def retrieve_relevant_chunks(
    question: str,
    identifiers: list[str],
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    document_ids = resolve_document_ids(identifiers, include_restricted)
    query_vector = embedding.vector_literal(embedding.embed_query(question))

    candidate_limit = max(limit * 3, 20)
    candidates = embedding_repository.retrieve(
        query_vector,
        document_ids,
        limit=candidate_limit,
    )
    return _rerank_or_dense(question, candidates, limit)


def search_full_corpus(
    question: str,
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    """Vector search across the ENTIRE indexed corpus, not just selected documents.

    Used by the agent's search_full_corpus tool when the caller's selected
    documents don't have enough evidence to answer from.
    """
    query_vector = embedding.vector_literal(embedding.embed_query(question))
    candidate_limit = max(limit * 3, 20)
    candidates = embedding_repository.retrieve_all(
        query_vector,
        limit=candidate_limit,
        include_restricted=include_restricted,
    )
    return _rerank_or_dense(question, candidates, limit)


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
