from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.pq import TransactionStatus
from pydantic import ValidationError

from app.core import database as database_module
from app.core.config import Settings
from app.core.database import Database, DatabaseUnavailableError, get_connection
from app.main import app
from app.modules.auth import router as auth_router
from app.modules.auth.dependencies import require_admin


def test_invalid_pool_sizes_are_rejected():
    with pytest.raises(ValidationError, match="MIN_SIZE"):
        Settings(_env_file=None, database_pool_min_size=3, database_pool_max_size=2)


async def test_disabled_database_never_creates_connections(monkeypatch):
    monkeypatch.setattr(
        database_module, "get_settings", lambda: Settings(_env_file=None, database_enabled=False)
    )
    instance = Database()
    await instance.connect()
    assert instance.pool is None
    assert instance.engine is None
    with pytest.raises(DatabaseUnavailableError, match="disabled"):
        instance.open_pool()


def test_registration_preserves_connection_capacity_503(monkeypatch):
    def busy(*_args):
        raise DatabaseUnavailableError("Database connection capacity is temporarily unavailable.")

    monkeypatch.setattr(auth_router, "create_user", busy)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "capacity-test",
                "email": "capacity@example.test",
                "password": "password",
                "password_confirmation": "password",
            },
        )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


def test_pool_statistics_require_administrator():
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/database-pool").status_code == 401
        app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
        try:
            response = client.get("/api/v1/admin/database-pool")
        finally:
            app.dependency_overrides.pop(require_admin, None)
    assert response.status_code == 200
    assert response.json()["scope"] == "per_process"
    assert "database_url" not in response.text


@pytest.mark.integration
def test_real_connections_are_reused_and_errors_rollback(postgres_repository):
    name = "pool_test_" + uuid4().hex
    with get_connection() as conn:
        pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        conn.execute(f"CREATE TABLE {name} (value integer)")
    try:
        with pytest.raises(ValueError, match="abort"):
            with get_connection() as conn:
                assert conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"] == pid
                conn.execute(f"INSERT INTO {name} VALUES (1)")
                raise ValueError("abort")
        assert conn.info.transaction_status == TransactionStatus.IDLE
        with get_connection() as conn:
            assert conn.execute(f"SELECT count(*) AS n FROM {name}").fetchone()["n"] == 0
            conn.execute(f"INSERT INTO {name} VALUES (2)")
        with get_connection() as conn:
            assert conn.execute(f"SELECT value FROM {name}").fetchone()["value"] == 2
        assert postgres_repository.pool_stats()["connections_num"] == 1
    finally:
        with get_connection() as conn:
            conn.execute(f"DROP TABLE {name}")


@pytest.mark.integration
def test_real_pool_allows_two_sessions_concurrently(postgres_repository):
    barrier = Barrier(2, timeout=3)

    def query():
        with get_connection() as conn:
            barrier.wait()
            return conn.execute("SELECT pg_backend_pid() AS pid, pg_sleep(0.1)").fetchone()["pid"]

    with ThreadPoolExecutor(max_workers=2) as workers:
        pids = list(workers.map(lambda _: query(), range(2)))
    assert len(set(pids)) == 2
    assert postgres_repository.pool_stats()["pool_size"] == 2


@pytest.mark.integration
@pytest.mark.parametrize(
    "postgres_repository",
    [{"database_pool_max_size": 1, "database_pool_timeout": 0.05}],
    indirect=True,
)
def test_real_pool_exhaustion_is_bounded_and_recovers(postgres_repository):
    with get_connection():
        with pytest.raises(DatabaseUnavailableError):
            with get_connection():
                pytest.fail("A second connection exceeded the pool maximum")
    with get_connection() as conn:
        assert conn.execute("SELECT 1 AS value").fetchone()["value"] == 1
    assert postgres_repository.pool_stats()["requests_errors"] >= 1
