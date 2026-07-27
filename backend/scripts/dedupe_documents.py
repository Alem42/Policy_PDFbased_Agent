"""Resolve exact-duplicate documents (same SHA-256) before migration 005.

Two documents with the same SHA-256 are byte-identical, so removing all but one
loses no content. For each duplicate group this keeps the MOST COMPLETE copy
(most chunks, tie-break earliest uploaded) and removes the rest.

Safe by default: prints a report and changes nothing. Pass --apply to delete the
redundant copies via the app's delete_document (DB rows cascade; the stored file
is removed too). Run from the backend/ directory:

    python scripts/dedupe_documents.py            # dry-run report
    python scripts/dedupe_documents.py --apply    # perform the cleanup

In Docker:
    docker compose exec backend python scripts/dedupe_documents.py [--apply]
"""

from __future__ import annotations

import argparse
import sys

from app.core.database import get_connection
from app.modules.documents.service import delete_document

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console
except Exception:
    pass


def _duplicate_rows() -> list[dict]:
    """Documents sharing a SHA-256, ordered so the copy to KEEP is first per group."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.original_filename, d.sha256, d.uploaded_at,
                   (SELECT count(*) FROM document_chunks c WHERE c.document_id = d.id) AS chunks,
                   (SELECT count(*) FROM document_pages p WHERE p.document_id = d.id) AS pages
            FROM documents d
            WHERE d.sha256 IN (
                SELECT sha256 FROM documents GROUP BY sha256 HAVING count(*) > 1
            )
            ORDER BY d.sha256, chunks DESC, d.uploaded_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _group_by_sha(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["sha256"], []).append(row)
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description="Deduplicate documents by SHA-256.")
    parser.add_argument(
        "--apply", action="store_true", help="Perform deletion (default: dry-run report only)."
    )
    args = parser.parse_args()

    groups = _group_by_sha(_duplicate_rows())
    if not groups:
        print("No duplicate-SHA-256 documents found. Nothing to do.")
        return 0

    redundant: list[dict] = []
    print(f"Found {len(groups)} duplicate-content group(s):\n")
    for sha, docs in groups.items():
        keep, *remove = docs  # first is the copy to keep (most chunks, earliest)
        redundant.extend(remove)
        print(f"  sha256 {sha[:16]}... ({len(docs)} copies)")
        print(f"    KEEP    {keep['id']}  {keep['original_filename']}"
              f"  (chunks={keep['chunks']}, pages={keep['pages']})")
        for doc in remove:
            print(f"    REMOVE  {doc['id']}  {doc['original_filename']}"
                  f"  (chunks={doc['chunks']}, pages={doc['pages']})")
        print()

    if not args.apply:
        print(f"Dry-run: would remove {len(redundant)} redundant document(s). "
              "Re-run with --apply to perform the cleanup.")
        return 0

    removed = 0
    for doc in redundant:
        try:
            delete_document(str(doc["id"]))  # DB cascade + file cleanup
            removed += 1
            print(f"Removed {doc['id']}  {doc['original_filename']}")
        except Exception as exc:
            print(f"FAILED to remove {doc['id']}: {exc}")
    print(f"\nDone. Removed {removed}/{len(redundant)} redundant document(s). "
          "You can now re-run migration 005.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
