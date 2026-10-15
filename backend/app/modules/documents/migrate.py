"""Apply migration 028 to the database configured by backend/.env and environment."""

from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row

from app.core.config import BACKEND_ROOT, get_settings
from app.core.database import normalise_database_url
from app.modules.documents.schema import validate_document_task_schema

MIGRATION_PATH = BACKEND_ROOT / "database/migrations/028_durable_document_tasks.sql"


def apply_migration(connection) -> None:
    """DDL and backfill commit together; serialize concurrent runs of this migration."""
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    with connection.transaction():
        connection.execute("SET LOCAL lock_timeout = '5s'")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("migration:028_durable_document_tasks",),
        )
        connection.execute(migration)
        validate_document_task_schema(connection)


def main() -> None:
    settings = get_settings()
    if not settings.database_enabled:
        raise SystemExit("Set DATABASE_ENABLED=true for the database to migrate.")
    dsn = normalise_database_url(settings.database_url)
    target = urlsplit(dsn)
    print(
        f"Applying migration 028 to {target.hostname}:{target.port or 5432}"
        f"{target.path} (credentials omitted)",
        flush=True,
    )
    with psycopg.connect(
        dsn, connect_timeout=settings.database_connect_timeout, row_factory=dict_row
    ) as connection:
        apply_migration(connection)
    print("Migration 028 committed. Existing users and documents were preserved.")


if __name__ == "__main__":
    main()
