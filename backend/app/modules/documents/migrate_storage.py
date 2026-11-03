"""Copy backend/data into a DATA_ROOT outside the code checkout.

Stop the API and workers, then from backend/ run:

    python -m app.modules.documents.migrate_storage --data-root E:/PolicyData           # plan only
    python -m app.modules.documents.migrate_storage --data-root E:/PolicyData --apply   # copy

Every file is copied, never moved, and each upload is checked against its stored
SHA-256 before any database row changes. Rows are rewritten in one transaction
to portable POSIX paths relative to DATA_ROOT/uploads. backend/data is left in
place; delete it yourself once the new location is verified.
"""

import argparse
import hashlib
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

from app.core.config import BACKEND_ROOT, ENV_FILE, LEGACY_DATA_DIR, get_settings
from app.core.database import normalise_database_url

SECRETS = {
    "app_secret": LEGACY_DATA_DIR / "app_secret",
    "settings.json": LEGACY_DATA_DIR / "settings.json",
    "settings.key": LEGACY_DATA_DIR / "secrets" / "settings.key",
}
LEGACY_UPLOAD_PREFIXES = ("data/pdfs/", "data/pdf/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def new_relative_path(row: dict) -> str | None:
    """Uploads-relative path for a legacy row, or None when it is already migrated."""
    stored = row["file_path"].replace("\\", "/")
    for prefix in LEGACY_UPLOAD_PREFIXES:
        if stored.startswith(prefix):
            return stored[len(prefix) :]
    if PurePosixPath(stored).is_absolute() or re.match(r"^[A-Za-z]:/", stored):
        return f"{row['id']}/{PurePosixPath(stored).name}"
    return None


def source_path(stored: str) -> Path:
    normalized = stored.replace("\\", "/")
    path = Path(normalized)
    return path if path.is_absolute() else BACKEND_ROOT / normalized


def plan_uploads(rows: list[dict], uploads: Path) -> tuple[list[tuple], list[str]]:
    moves, problems = [], []
    for row in rows:
        relative = new_relative_path(row)
        if relative is None:
            continue
        source = source_path(row["file_path"])
        if not source.is_file():
            problems.append(f"missing file for {row['id']}: {row['file_path']}")
            continue
        moves.append((row, source, uploads / relative, relative))
    return moves, problems


def write_env(data_root: Path) -> None:
    line = f"DATA_ROOT={data_root.as_posix()}"
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    if re.search(r"^DATA_ROOT=", text, re.M):
        text = re.sub(r"^DATA_ROOT=.*$", line, text, flags=re.M)
    else:
        text = (
            text.rstrip("\n") + f"\n\n# Data and secrets live outside the code checkout.\n{line}\n"
        )
    ENV_FILE.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Copy files and update the database")
    parser.add_argument("--skip-model-cache", action="store_true")
    parser.add_argument("--write-env", action="store_true", help="Set DATA_ROOT in backend/.env")
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    if data_root == LEGACY_DATA_DIR.resolve() or data_root.is_relative_to(BACKEND_ROOT.parent):
        raise SystemExit("Choose a DATA_ROOT outside the code checkout.")
    settings = get_settings()
    if not settings.database_enabled:
        raise SystemExit("Set DATABASE_ENABLED=true for the database to migrate.")
    uploads, secrets_dir = data_root / "uploads", data_root / "secrets"

    dsn = normalise_database_url(settings.database_url)
    target = urlsplit(dsn)
    print(f"Database: {target.hostname}:{target.port or 5432}{target.path} (credentials omitted)")
    print(f"From:     {LEGACY_DATA_DIR}\nTo:       {data_root}")

    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT id, file_path, sha256 FROM documents ORDER BY id"
        ).fetchall()
        moves, problems = plan_uploads(rows, uploads)

        secrets = [(name, source) for name, source in SECRETS.items() if source.is_file()]
        for name, source in secrets:
            existing = secrets_dir / name
            if existing.exists() and existing.read_bytes() != source.read_bytes():
                problems.append(f"{existing} already exists with different content")
        model_cache = LEGACY_DATA_DIR / "model_cache"
        copy_models = model_cache.is_dir() and not args.skip_model_cache

        print(f"\nUploads to copy: {len(moves)} of {len(rows)} documents")
        print(f"Secrets to copy: {', '.join(name for name, _ in secrets) or 'none'}")
        print(f"Model cache:     {'copy ' + str(model_cache) if copy_models else 'skip'}")
        referenced = {move[1].parent.resolve() for move in moves}
        legacy_uploads = LEGACY_DATA_DIR / "pdfs"
        orphans = [
            path.name
            for path in (legacy_uploads.iterdir() if legacy_uploads.is_dir() else [])
            if path.is_dir() and path.resolve() not in referenced
        ]
        if orphans:
            print(f"Not copied (no database row): {len(orphans)} folders in {legacy_uploads}")
        for problem in problems:
            print(f"PROBLEM: {problem}")
        if problems:
            raise SystemExit("Nothing was changed. Resolve the problems above first.")
        if not args.apply:
            print("\nPlan only. Re-run with --apply to copy files and update the database.")
            return

        for row, source, destination, _ in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if sha256(destination) != row["sha256"]:
                raise SystemExit(f"Checksum mismatch after copying {source}; database unchanged.")
        secrets_dir.mkdir(parents=True, exist_ok=True)
        for name, source in secrets:
            shutil.copy2(source, secrets_dir / name)
        if copy_models:
            shutil.copytree(model_cache, data_root / "model-cache", dirs_exist_ok=True)
        (data_root / "logs").mkdir(exist_ok=True)

        with connection.transaction():
            for row, _, _, relative in moves:
                updated = connection.execute(
                    "UPDATE documents SET file_path = %s WHERE id = %s AND file_path = %s",
                    (relative, row["id"], row["file_path"]),
                ).rowcount
                if updated != 1:
                    raise SystemExit(f"Document {row['id']} changed during migration; rolled back.")
        print(f"\nCopied and verified {len(moves)} uploads; database paths updated.")

    if args.write_env:
        write_env(data_root)
        print(f"Set DATA_ROOT={data_root.as_posix()} in {ENV_FILE}")
    else:
        print(f"Now set DATA_ROOT={data_root.as_posix()} for the API and workers.")
    print(f"{LEGACY_DATA_DIR} was not modified; remove it after verifying the application.")


if __name__ == "__main__":
    main()
