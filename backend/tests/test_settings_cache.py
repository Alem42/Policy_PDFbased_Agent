import json
from contextlib import contextmanager

from app.core import settings_store
from app.core.settings_store import SingleRowSettings
from app.modules.settings import repository as settings_repository_module
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schemas import RuntimeSettings


def test_runtime_settings_are_cached_and_defensively_copied(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"provider_api_keys": {"zhipu": "first-key"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_repository_module, "SETTINGS_PATH", settings_path)
    repository = SettingsRepository()

    first = repository.load()
    first.provider_api_keys["zhipu"] = "mutated-outside-cache"
    settings_path.write_text(
        json.dumps({"provider_api_keys": {"zhipu": "changed-on-disk"}}),
        encoding="utf-8",
    )

    assert repository.load().provider_api_keys["zhipu"] == "first-key"

    repository.save(RuntimeSettings(provider_api_keys={"zhipu": "saved-key"}))

    assert repository.load().provider_api_keys["zhipu"] == "saved-key"
    assert json.loads(settings_path.read_text(encoding="utf-8"))["provider_api_keys"] == {
        "zhipu": "saved-key"
    }


def test_runtime_settings_invalidation_reloads_the_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings_repository_module, "SETTINGS_PATH", settings_path)
    repository = SettingsRepository()
    assert repository.load().provider_api_keys == {}

    settings_path.write_text(
        json.dumps({"provider_api_keys": {"zhipu": "reloaded-key"}}),
        encoding="utf-8",
    )
    repository.invalidate()

    assert repository.load().provider_api_keys["zhipu"] == "reloaded-key"


def test_single_row_settings_read_database_once_and_update_cache(monkeypatch):
    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.config = {"provider": "local"}
            self.selects = 0
            self.writes = 0

        def execute(self, statement, values=None):
            if statement.lstrip().startswith("SELECT"):
                self.selects += 1
                return Result({"config": self.config})
            self.writes += 1
            self.config = json.loads(values[0])
            return Result(None)

        def commit(self):
            return None

    connection = Connection()

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(settings_store, "get_connection", fake_connection)
    store = SingleRowSettings("embedding_settings")

    assert store.load() == {"provider": "local"}
    assert store.load() == {"provider": "local"}
    assert connection.selects == 1

    store.save('{"provider": "api"}')

    assert store.load() == {"provider": "api"}
    assert connection.selects == 1
    assert connection.writes == 1


def test_single_row_settings_invalidation_reloads_database(monkeypatch):
    class Result:
        def __init__(self, config):
            self.config = config

        def fetchone(self):
            return {"config": self.config}

    state = {"config": {"enabled": True}, "selects": 0}

    class Connection:
        def execute(self, statement, values=None):
            state["selects"] += 1
            return Result(state["config"])

    @contextmanager
    def fake_connection():
        yield Connection()

    monkeypatch.setattr(settings_store, "get_connection", fake_connection)
    store = SingleRowSettings("reranking_settings")
    assert store.load() == {"enabled": True}

    state["config"] = {"enabled": False}
    store.invalidate()

    assert store.load() == {"enabled": False}
    assert state["selects"] == 2
