from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import UploadFile

from app.core.database import get_connection
from app.modules.documents.exceptions import DuplicateDocumentError
from app.modules.documents.processing_queue import document_processing_queue
from app.modules.documents.repositories.content import document_content_repository
from app.modules.documents.repositories.documents import document_repository
from app.modules.documents.service import save_upload

DATA = Path(__file__).parent / "data"
CORPUS = DATA / "corpus-v1"
TEST_TAG = "test-corpus"


def manifest() -> dict:
    return json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))


def cases() -> list[dict]:
    return json.loads((DATA / "cases-v1.json").read_text(encoding="utf-8"))["cases"]


def verified_files() -> list[tuple[dict, Path]]:
    result = []
    for entry in manifest()["documents"]:
        path = (CORPUS / entry["local_path"]).resolve()
        if not path.is_relative_to(CORPUS.resolve()) or not path.is_file():
            raise ValueError(f"Missing/invalid corpus file: {entry['id']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Corpus checksum mismatch: {entry['id']}")
        result.append((entry, path))
    return result


def mapping() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT source_id, document_id FROM evaluation_corpus_documents WHERE corpus_id=%s",
            (manifest()["corpus_id"],),
        ).fetchall()
    return {row["source_id"]: str(row["document_id"]) for row in rows}


def _register_mapping(entry, identifier, metadata, reused):
    with get_connection() as conn:
        old = conn.execute(
            "SELECT keywords FROM document_metadata WHERE document_id=%s", (identifier,)
        ).fetchone()
        keywords = sorted(set((old or {}).get("keywords") or []) | set(metadata["keywords"]))
        # Reusing a user's exact PDF must not overwrite their reviewed metadata.
        payload = {"keywords": keywords} if reused else {**metadata, "keywords": keywords}
        document_content_repository.update_metadata(identifier, payload, connection=conn)
        conn.execute(
            "INSERT INTO evaluation_corpus_documents (corpus_id,source_id,document_id,sha256) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (corpus_id,source_id) DO UPDATE "
            "SET document_id=EXCLUDED.document_id,sha256=EXCLUDED.sha256",
            (manifest()["corpus_id"], entry["id"], identifier, entry["sha256"]),
        )


async def install(admin_id: str) -> dict:
    # Validate the entire pack before the first write. Repeated imports reuse SHA256 identity.
    import asyncio

    files = await asyncio.to_thread(verified_files)
    installed = []
    for entry, path in files:
        row = await asyncio.to_thread(document_repository.find_by_checksum, entry["sha256"])
        reused = bool(row)
        metadata = {
            "title": entry["title"],
            "country_region": entry["region"],
            "language": entry["language"],
            "year": int(entry["document_version"][:4]),
            "keywords": [TEST_TAG, manifest()["corpus_id"]],
        }
        if row is None:
            try:
                with path.open("rb") as stream:
                    row = await save_upload(
                        UploadFile(filename=path.name, file=stream, size=path.stat().st_size),
                        source_url=entry["source_page"],
                        imported_by=admin_id,
                        imported_via="evaluation_corpus",
                        durable=True,
                        metadata=metadata,
                        idempotency_key=f"corpus-v1:{entry['id']}",
                    )
            except DuplicateDocumentError as exc:
                row = {"id": exc.existing_id}
                reused = True
        identifier = str(row["id"])
        await asyncio.to_thread(_register_mapping, entry, identifier, metadata, reused)
        installed.append({"source_id": entry["id"], "document_id": identifier, "reused": reused})
    document_processing_queue.notify()
    return {"documents": installed, "tag": TEST_TAG}
