from app.core.database import get_connection
from app.modules.documents.repositories.embeddings import ensure_vector_table

TABLE = "chunk_vectors_lock_probe_8"


def _share_locks(connection, table):
    return connection.execute(
        """
        SELECT mode FROM pg_locks
        WHERE pid = pg_backend_pid() AND relation = to_regclass(%s)
          AND mode IN ('ShareLock', 'AccessExclusiveLock', 'ShareRowExclusiveLock')
        """,
        (f"public.{table}",),
    ).fetchall()


def test_existing_vector_table_is_not_locked_by_ensure(postgres_repository):
    with get_connection() as connection:
        ensure_vector_table(connection, TABLE, 8)  # first call creates table and index
    try:
        with get_connection() as connection:
            ensure_vector_table(connection, TABLE, 8)
            # A held SHARE lock here is what deadlocked concurrent document workers.
            assert _share_locks(connection, TABLE) == []
            index = connection.execute(
                "SELECT to_regclass(%s) AS i", (f"public.{TABLE}_hnsw",)
            ).fetchone()
            assert index["i"] is not None
    finally:
        with get_connection() as connection:
            connection.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
