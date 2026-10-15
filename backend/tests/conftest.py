import os

os.environ["DATABASE_ENABLED"] = "false"

import pytest

from app.core import database as database_module
from app.core.config import Settings


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
