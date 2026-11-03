import os
import tempfile
from pathlib import Path

# Point every writable location at a throwaway directory before the app is imported:
# a test that reached the real settings.json once rewrote it with a test-only key.
_TEST_DATA = Path(tempfile.mkdtemp(prefix="policy-tests-"))
os.environ.update(
    {
        "DATABASE_ENABLED": "false",
        "DATA_ROOT": str(_TEST_DATA),
        "RUNTIME_SETTINGS_PATH": str(_TEST_DATA / "secrets" / "settings.json"),
        "APP_SECRET_FILE": str(_TEST_DATA / "secrets" / "app_secret"),
        "SETTINGS_KEY_FILE": str(_TEST_DATA / "secrets" / "settings.key"),
        "DOCUMENT_STORAGE_DIR": str(_TEST_DATA / "uploads"),
    }
)
_REAL_DATA = Path(__file__).resolve().parents[1] / "data"


def _real_data_stamp() -> dict:
    files = [_REAL_DATA / name for name in ("settings.json", "app_secret")]
    files += [
        _REAL_DATA / "secrets" / name for name in ("settings.json", "app_secret", "settings.key")
    ]
    return {str(path): path.stat().st_mtime_ns for path in files if path.exists()}


_REAL_DATA_BEFORE = _real_data_stamp()

import pytest  # noqa: E402

from app.core import database as database_module  # noqa: E402
from app.core import secret_box  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    if _real_data_stamp() != _REAL_DATA_BEFORE:
        raise RuntimeError("Tests modified the real backend/data secrets; isolate the test.")


@pytest.fixture(autouse=True)
def _test_settings_key(monkeypatch):
    """Never create or read the real secrets/settings.key from tests."""
    from cryptography.fernet import Fernet

    monkeypatch.setattr(get_settings(), "settings_encryption_key", Fernet.generate_key().decode())
    secret_box.reset_cache()
    yield
    secret_box.reset_cache()


@pytest.fixture
def postgres_repository(monkeypatch, request):
    """Opt-in real PostgreSQL tests; never fall back to the application's .env."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an initialized disposable PostgreSQL database.")
    options = {
        "database_enabled": True,
        "database_url": url,
        "database_pool_min_size": 1,
        "database_pool_max_size": 2,
        "database_pool_timeout": 0.3,
        "database_pool_pre_ping": True,
    }
    options.update(getattr(request, "param", {}))
    settings = Settings(_env_file=None, **options)
    instance = database_module.Database()
    monkeypatch.setattr(database_module, "get_settings", lambda: settings)
    monkeypatch.setattr(database_module, "database", instance)
    instance.open_pool()
    try:
        yield instance
    finally:
        instance.close_pool()
