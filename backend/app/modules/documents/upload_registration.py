"""Atomically register a complete file, its task, and an optional request key."""

import hashlib
import json

from psycopg.errors import UniqueViolation

from app.core.database import get_connection
from app.modules.documents.exceptions import DuplicateDocumentError
from app.modules.documents.file_store import StagedUpload, document_file_store
from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.repositories.helpers import row_to_metadata
from app.modules.documents.repositories.tasks import document_task_repository


class IdempotencyConflict(ValueError):
    pass


def register_staged_upload(
    staged: StagedUpload,
    document_id: str,
    *,
    metadata: dict,
    source_url: str | None,
    canonical_url: str | None,
    imported_by: str | None,
    imported_via: str | None,
    idempotency_key: str | None,
) -> dict:
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "sha256": staged.checksum,
                "filename": staged.filename,
                "metadata": metadata,
                "source_url": source_url,
                "canonical_url": canonical_url,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    published = None
    try:
        with get_connection() as conn:
            if idempotency_key:
                if not imported_by:
                    raise ValueError("Request idempotency requires an authenticated uploader.")
                conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"document-upload:{imported_by}:{idempotency_key}",),
                )
                previous = conn.execute(
                    "SELECT * FROM document_upload_requests "
                    "WHERE actor_id = %s AND idempotency_key = %s",
                    (imported_by, idempotency_key),
                ).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise IdempotencyConflict(
                            "This Idempotency-Key was already used for a different upload."
                        )
                    record = document_repository.get_record(
                        str(previous["document_id"]), connection=conn
                    )
                    return {
                        **row_to_metadata(record),
                        "task_id": str(previous["task_id"]),
                        "replayed": True,
                    }
            existing = document_repository.find_by_checksum(staged.checksum, connection=conn)
            if existing:
                raise DuplicateDocumentError(str(existing["id"]), existing["original_filename"])
            published = document_file_store.publish_upload(staged, document_id)
            document_repository.create(
                document_id=document_id,
                original_filename=staged.filename,
                stored_filename=published.name,
                file_path=document_file_store.relative_path(published),
                file_size=staged.file_size,
                checksum=staged.checksum,
                mime_type=document_file_store.mime_type_for(staged.filename),
                source_url=source_url,
                canonical_url=canonical_url,
                imported_by=imported_by,
                imported_via=imported_via,
                connection=conn,
            )
            if metadata:
                document_content_repository.update_metadata(document_id, metadata, connection=conn)
            task = document_task_repository.enqueue(document_id, connection=conn)
            if idempotency_key:
                conn.execute(
                    "INSERT INTO document_upload_requests "
                    "(actor_id, idempotency_key, fingerprint, document_id, task_id) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (imported_by, idempotency_key, fingerprint, document_id, task["id"]),
                )
            result = {
                **row_to_metadata(document_repository.get_record(document_id, connection=conn)),
                "task_id": str(task["id"]),
                "replayed": False,
            }
        return result
    except Exception as exc:
        if published is not None:
            # On an ambiguous COMMIT/network failure, retain a possibly registered file.
            try:
                document_repository.get_record(document_id)
            except FileNotFoundError:
                document_file_store.delete(published)
            except Exception:
                pass
        if isinstance(exc, UniqueViolation):
            if exc.diag.constraint_name == "documents_sha256_key":
                existing = document_repository.find_by_checksum(staged.checksum)
            elif exc.diag.constraint_name == "uq_documents_canonical_url":
                existing = document_repository.find_by_source_url(canonical_url or source_url or "")
            else:
                existing = None
            if existing:
                raise DuplicateDocumentError(
                    str(existing["id"]), existing["original_filename"]
                ) from exc
        raise
