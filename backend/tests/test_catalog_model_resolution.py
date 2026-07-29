from app.modules.catalog import repository as catalog_repository
from app.modules.catalog import service as catalog_service
from app.modules.embedding import service as embedding_service
from app.modules.embedding.settings import EmbeddingConfig
from app.modules.settings import service as settings_service


def test_catalog_is_filtered_by_capability():
    embedding_entries = catalog_service.get_catalog("embedding")["entries"]
    rerank_entries = catalog_service.get_catalog("rerank")["entries"]

    assert {entry["model"] for entry in embedding_entries} == {
        "embedding-2",
        "embedding-3",
    }
    assert {entry["capability"] for entry in embedding_entries} == {"embedding"}
    assert {entry["model"] for entry in rerank_entries} == {"rerank"}
    assert {entry["capability"] for entry in rerank_entries} == {"rerank"}


def test_embedding_catalog_pick_resolves_central_key(monkeypatch):
    monkeypatch.setattr(
        catalog_service,
        "resolve_base_url",
        lambda provider, model, capability: "https://open.bigmodel.cn/api/paas/v4",
    )
    monkeypatch.setattr(
        settings_service,
        "get_llm_api_key",
        lambda provider: ("zhipu-key", "settings"),
    )
    config = EmbeddingConfig(
        provider="api",
        api_provider="zhipu",
        api_model="embedding-3",
        dimensions=2048,
    )

    resolved = embedding_service._resolved_config(config)

    assert resolved.api_base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert resolved.api_key == "zhipu-key"


def test_manual_embedding_keeps_manually_entered_credentials():
    config = EmbeddingConfig(
        provider="api",
        api_provider="__manual__",
        api_base_url="https://example.test/v1",
        api_key="manual-key",
        api_model="custom-embedding",
    )

    assert embedding_service._resolved_config(config) == config


def test_database_catalog_is_loaded_once_and_filtered_from_cache(monkeypatch):
    calls = {"seed": 0, "list": 0}
    rows = [
        {
            "provider": "zhipu",
            "provider_label": "Zhipu 智谱",
            "capability": "embedding",
            "model": "embedding-3",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "endpoint": "/embeddings",
            "dimensions": 2048,
            "openai_compatible": True,
            "notes": None,
            "sort_order": 0,
        },
        {
            "provider": "zhipu",
            "provider_label": "Zhipu 智谱",
            "capability": "rerank",
            "model": "rerank",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "endpoint": "/rerank",
            "dimensions": None,
            "openai_compatible": True,
            "notes": None,
            "sort_order": 1,
        },
    ]

    monkeypatch.setattr(
        catalog_repository,
        "get_settings",
        lambda: type("Settings", (), {"database_enabled": True})(),
    )
    monkeypatch.setattr(catalog_repository, "_defaults_synced", False)
    monkeypatch.setattr(
        catalog_repository.model_catalog_repository,
        "seed",
        lambda entries: calls.__setitem__("seed", calls["seed"] + 1),
    )

    def list_rows():
        calls["list"] += 1
        return rows

    monkeypatch.setattr(catalog_repository.model_catalog_repository, "list", list_rows)
    catalog_repository.invalidate_catalog_cache()

    try:
        assert len(catalog_repository.catalog_entries("embedding")) == 1
        assert len(catalog_repository.catalog_entries("rerank")) == 1
        assert len(catalog_repository.catalog_entries()) == 2
        assert calls == {"seed": 1, "list": 1}
    finally:
        catalog_repository.invalidate_catalog_cache()


def test_catalog_write_invalidates_cache(monkeypatch):
    invalidated = {"called": False}
    monkeypatch.setattr(catalog_service.model_catalog_repository, "add", lambda entry: None)
    monkeypatch.setattr(
        catalog_service,
        "invalidate_catalog_cache",
        lambda: invalidated.__setitem__("called", True),
    )

    catalog_service.add_entry(
        {
            "provider": "test",
            "capability": "embedding",
            "model": "test-embedding",
        }
    )

    assert invalidated["called"] is True
