"""Bulk-register a folder of documents and queue them for the document workers.

From backend/, with the same environment as the API:

    python -m scripts.import_documents <folder> [--manifest manifest.csv] [--limit N] [--dry-run]

Each file is copied into DATA_ROOT/uploads and registered with its metadata and a
durable ingest task in one transaction, exactly like an API upload, but without
HTTP, upload rate limits or a per-request size check. Files whose SHA-256 already
exists in the library are skipped, so re-running the import is safe. Workers (in
the API process or `python -m app.modules.documents.worker`) do the processing.

The optional manifest is a CSV with a `filename` column plus any upload metadata
columns: title, source_organisation, country_or_region, published_year,
source_url, policy_area, tags (separated by `;`).
"""

import argparse
import csv
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_connection  # noqa: E402
from app.modules.documents.file_store import SUPPORTED_MIME_TYPES, document_file_store  # noqa: E402
from app.modules.documents.repositories.content import document_content_repository  # noqa: E402
from app.modules.documents.repositories.documents import document_repository  # noqa: E402
from app.modules.documents.repositories.tasks import document_task_repository  # noqa: E402

METADATA_FIELDS = (
    "title",
    "source_organisation",
    "country_or_region",
    "published_year",
    "source_url",
    "policy_area",
)


def read_manifest(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["filename"]: row for row in csv.DictReader(handle)}


def metadata_for(row: dict) -> dict:
    metadata = {field: row[field] for field in METADATA_FIELDS if row.get(field)}
    if metadata.get("published_year"):
        metadata["published_year"] = int(metadata["published_year"])
    if row.get("tags"):
        metadata["tags"] = [tag.strip() for tag in row["tags"].split(";") if tag.strip()]
    return metadata


def import_file(path: Path, row: dict) -> str:
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if not document_file_store.is_valid_content(path.name, content):
        return "invalid"
    if document_repository.find_by_checksum(checksum):
        return "duplicate"
    document_id = str(uuid4())
    stored = document_file_store.copy(path, document_id)
    try:
        with get_connection() as conn:
            document_repository.create(
                document_id=document_id,
                original_filename=path.name,
                stored_filename=stored.name,
                file_path=document_file_store.relative_path(stored),
                file_size=len(content),
                checksum=checksum,
                mime_type=document_file_store.mime_type_for(path.name),
                source_url=row.get("source_url") or None,
                canonical_url=row.get("source_url") or None,
                imported_via="bulk_import",
                connection=conn,
            )
            metadata = metadata_for(row)
            if metadata:
                document_content_repository.update_metadata(document_id, metadata, connection=conn)
            document_task_repository.enqueue(document_id, connection=conn)
    except Exception:
        document_file_store.delete(stored)
        raise
    return "queued"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = read_manifest(args.manifest)
    files = sorted(
        path
        for path in args.folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_MIME_TYPES
    )
    if manifest:
        files = [path for path in files if path.name in manifest]
    files = files[: args.limit] if args.limit else files
    print(f"{len(files)} files in {args.folder}" + (" (dry run)" if args.dry_run else ""))
    if args.dry_run:
        return
    counts: dict[str, int] = {}
    for index, path in enumerate(files, 1):
        try:
            outcome = import_file(path, manifest.get(path.name, {}))
        except Exception as exc:  # noqa: BLE001 - keep importing the rest
            outcome = "error"
            print(f"error: {path.name}: {exc}", flush=True)
        counts[outcome] = counts.get(outcome, 0) + 1
        if index % 100 == 0:
            print(f"{index}/{len(files)} {counts}", flush=True)
    print(f"done: {counts}")


if __name__ == "__main__":
    main()
