"""Read/manage documents already registered in the library.

Black box: given a document identifier (UUID or filename), resolve its
record, content, chunks, or on-disk file — and apply admin edits
(metadata, governance, deletion). Owns no ingestion or retrieval logic;
`pipeline.py` and `retrieval.py` both depend on this module for document
lookup, never the other way around.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.documents.extraction import extract_document
from app.modules.documents.file_store import document_file_store
from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.embeddings import embedding_repository
from app.modules.documents.repositories.helpers import row_to_metadata

_LOSSY_TITLE = re.compile(r"[?？]{3,}")


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
    title = payload.get("title")
    if isinstance(title, str) and _LOSSY_TITLE.search(title):
        raise ValueError(
            "The title appears to contain encoding-damaged text (a run of question marks). "
            "Submit UTF-8 text or keep the automatically generated English title."
        )
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
