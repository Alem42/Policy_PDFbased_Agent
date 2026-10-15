from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app import main as api_module
from app.core.config import Settings
from app.core.database import get_connection
from app.modules.documents import worker as worker_module
from app.modules.documents.migrate import apply_migration
from app.modules.documents.schema import (
    DocumentTaskSchemaError,
    validate_document_task_schema,
)


@pytest.mark.parametrize("entrypoint", ["api", "worker"])
async def test_missing_schema_stops_startup_and_closes_connections(monkeypatch, entrypoint):
    module = api_module if entrypoint == "api" else worker_module
    connect, disconnect = AsyncMock(), AsyncMock()
    start = AsyncMock()
    monkeypatch.setattr(module.database, "connect", connect)
    monkeypatch.setattr(module.database, "disconnect", disconnect)
    monkeypatch.setattr(
        module, "get_settings", lambda: Settings(_env_file=None, database_enabled=True)
    )
    monkeypatch.setattr(
        module,
        "validate_document_task_schema",
        Mock(side_effect=DocumentTaskSchemaError("missing document_tasks")),
    )
    if entrypoint == "api":
        checkpointer = AsyncMock()
        monkeypatch.setattr(module, "init_checkpointer", checkpointer)
        monkeypatch.setattr(module, "close_checkpointer", AsyncMock())
        monkeypatch.setattr(module.document_processing_queue, "start", start)
        monkeypatch.setattr(module.document_processing_queue, "stop", AsyncMock())
        with pytest.raises(DocumentTaskSchemaError, match="document_tasks"):
            async with module.lifespan(module.app):
                pytest.fail("Startup must not accept requests with missing tables")
        checkpointer.assert_not_awaited()
    else:
        queue = Mock(start=start, stop=AsyncMock())
        monkeypatch.setattr(module, "DocumentProcessingQueue", lambda **kwargs: queue)
        with pytest.raises(DocumentTaskSchemaError, match="document_tasks"):
            await module.run(3)
    connect.assert_awaited_once()
    start.assert_not_awaited()
    disconnect.assert_awaited_once()


@pytest.fixture
def old_schema(postgres_repository):
    """A pre-028 schema isolated from every existing test table."""
    name = "migration_test_" + uuid4().hex
    with get_connection() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        connection.execute(
            sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(name))
        )
        connection.execute("CREATE TABLE app_users (id uuid PRIMARY KEY)")
        connection.execute("CREATE TABLE documents (id uuid PRIMARY KEY, status text)")
        user = uuid4()
        ready, pending = uuid4(), uuid4()
        connection.execute("INSERT INTO app_users VALUES (%s)", (user,))
        connection.execute(
            "INSERT INTO documents VALUES (%s, 'ready'), (%s, 'uploaded')", (ready, pending)
        )
        try:
            yield connection, ready, pending
        finally:
            connection.execute("SET LOCAL search_path TO public")
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


@pytest.mark.integration
def test_migration_repairs_old_schema_preserves_data_and_backfills_once(old_schema):
    connection, ready, pending = old_schema
    with pytest.raises(DocumentTaskSchemaError, match="python -m app.modules.documents.migrate"):
        validate_document_task_schema(connection)
    apply_migration(connection)
    validate_document_task_schema(connection)
    apply_migration(connection)
    assert connection.execute("SELECT count(*) AS n FROM app_users").fetchone()["n"] == 1
    assert connection.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 2
    assert (
        connection.execute("SELECT status FROM documents WHERE id=%s", (ready,)).fetchone()[
            "status"
        ]
        == "ready"
    )
    tasks = connection.execute(
        "SELECT document_id, status, attempts FROM document_tasks"
    ).fetchall()
    assert tasks == [{"document_id": pending, "status": "queued", "attempts": 0}]
    assert (
        connection.execute("SELECT count(*) AS n FROM document_upload_requests").fetchone()["n"]
        == 0
    )


@pytest.mark.integration
def test_failed_migration_rolls_back_ddl_and_backfill(old_schema):
    connection, _, _ = old_schema
    connection.execute("ALTER TABLE app_users DROP CONSTRAINT app_users_pkey")
    with pytest.raises(psycopg.errors.InvalidForeignKey):
        apply_migration(connection)
    assert connection.execute("SELECT to_regclass('document_tasks') AS t").fetchone()["t"] is None
    assert connection.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 2
