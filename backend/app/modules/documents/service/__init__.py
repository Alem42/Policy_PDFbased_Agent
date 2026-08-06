"""Public document-service API.

Three black boxes, layered on top of each other:
  - `library`: read/manage documents already in the catalogue.
  - `pipeline`: ingestion (upload, extract, chunk, embed, rescan, re-embed,
    web import) — depends on `library` for lookup/cleanup.
  - `retrieval`: RAG chunk retrieval for chat/agent — depends on `library`
    for identifier resolution.

Every name below is re-exported so existing callers
(`from app.modules.documents.service import X` / `from app.modules.documents
import service; service.X`) keep working unchanged. New code should prefer
importing the specific submodule (`from app.modules.documents.service import
library`) to make the dependency explicit.
"""

from __future__ import annotations

from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.embedding import service as embedding

from . import library, pipeline, retrieval
from .library import (
    delete_document,
    documents_have_embeddings,
    extract_pages,
    get_document,
    get_document_chunks,
    get_document_detail,
    list_documents,
    read_documents,
    resolve_document_file,
    resolve_document_ids,
    update_document_governance,
    update_document_metadata,
)
from .pipeline import (
    L3_NEAR_DUPLICATE_DISTANCE,
    copy_file_into_library,
    mark_document_queued,
    prepare_full_rescan,
    prepare_reembed,
    process_document,
    reembed_and_mark,
    reembed_document,
    save_upload,
    save_web_import,
    sync_existing_documents,
)
from .retrieval import retrieve_relevant_chunks, search_full_corpus

__all__ = [
    "L3_NEAR_DUPLICATE_DISTANCE",
    "copy_file_into_library",
    "delete_document",
    "document_content_repository",
    "document_repository",
    "documents_have_embeddings",
    "embedding",
    "embedding_repository",
    "extract_pages",
    "get_document",
    "get_document_chunks",
    "get_document_detail",
    "library",
    "list_documents",
    "mark_document_queued",
    "pipeline",
    "prepare_full_rescan",
    "prepare_reembed",
    "process_document",
    "read_documents",
    "reembed_and_mark",
    "reembed_document",
    "resolve_document_file",
    "resolve_document_ids",
    "retrieval",
    "retrieve_relevant_chunks",
    "save_upload",
    "save_web_import",
    "search_full_corpus",
    "sync_existing_documents",
    "update_document_governance",
    "update_document_metadata",
]
