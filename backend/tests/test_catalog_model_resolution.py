from app.core import llm_providers
from app.modules.catalog import repository as catalog_repository
from app.modules.catalog import service as catalog_service
from app.modules.embedding import service as embedding_service
from app.modules.embedding.settings import EmbeddingConfig
from app.modules.settings import service as settings_service


def test_catalog_is_filtered_by_capability():
    embedding_entries = catalog_service.get_catalog("embedding")["entries"]
    rerank_entries = catalog_service.get_catalog("rerank")["entries"]

    zhipu_embedding_models = {
        entry["model"]
        for entry in embedding_entries
        if entry["provider"] == "zhipu"
    }
    assert zhipu_embedding_models == {
        "embedding-2",
        "embedding-3",
    }
    assert {entry["capability"] for entry in embedding_entries} == {"embedding"}
    assert {entry["model"] for entry in rerank_entries} == {"rerank"}
    assert {entry["capability"] for entry in rerank_entries} == {"rerank"}


def test_default_chat_and_openai_embedding_endpoints_are_catalogued():
    catalog = catalog_service.get_catalog()

    assert any(
        entry["provider"] == "deepseek"
        and entry["capability"] == "chat"
        and entry["model"] == "deepseek-v4-flash"
        for entry in catalog["entries"]
    )
    assert any(
        entry["provider"] == "openai"
        and entry["capability"] == "embedding"
        and entry["model"] == "text-embedding-3-large"
        and entry["dimensions"] == 3072
        for entry in catalog["entries"]
    )


def test_chinese_only_catalog_text_gets_an_english_display_label(monkeypatch):
    monkeypatch.setattr(
        catalog_service,
        "catalog_entries",
        lambda capability=None: [
            {
                "provider": "zhipu",
                "provider_label": "智谱",
                "capability": "voice",
                "model": "音色列表",
                "base_url": "https://example.test",
                "endpoint": "/voice/list",
                "notes": "仅中文说明",
            }
        ],
    )

    entry = catalog_service.get_catalog()["entries"][0]

    assert entry["provider_label_display"] == "Zhipu"
    assert entry["model_display"] == "Voice list"
    assert entry["notes_display"] == "Voice capability"
    assert entry["model"] == "音色列表"


def test_mixed_or_english_catalog_text_is_preserved(monkeypatch):
    monkeypatch.setattr(
        catalog_service,
        "catalog_entries",
        lambda capability=None: [
            {
                "provider": "zhipu",
                "provider_label": "Zhipu 智谱",
                "capability": "embedding",
                "model": "embedding-3",
                "base_url": "https://example.test",
                "endpoint": "/embeddings",
                "notes": "Variable dimensions",
            }
        ],
    )

    entry = catalog_service.get_catalog()["entries"][0]

    assert entry["provider_label_display"] == "Zhipu 智谱"
    assert entry["model_display"] == "embedding-3"
    assert entry["notes_display"] == "Variable dimensions"


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
    monkeypatch.setattr(
        catalog_service,
        "provider_entries",
        lambda: [{"id": "test", "label": "Test provider"}],
    )
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


def test_non_embedding_endpoint_discards_dimensions(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        catalog_service,
        "provider_entries",
        lambda: [
            {
                "id": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
            }
        ],
    )
    monkeypatch.setattr(
        catalog_service.model_catalog_repository,
        "add",
        lambda entry: saved.update(entry),
    )
    monkeypatch.setattr(catalog_service, "invalidate_catalog_cache", lambda: None)

    catalog_service.add_entry(
        {
            "provider": "openai",
            "capability": "chat",
            "model": "test-chat",
            "base_url": "https://api.openai.com/v1",
            "endpoint": "/chat/completions",
            "dimensions": 1234,
        }
    )

    assert saved["provider_label"] == "OpenAI"
    assert saved["dimensions"] is None


def test_endpoint_requires_registered_provider(monkeypatch):
    monkeypatch.setattr(catalog_service, "provider_entries", lambda: [])

    try:
        catalog_service.add_entry(
            {
                "provider": "unknown",
                "capability": "embedding",
                "model": "unknown-model",
            }
        )
    except ValueError as exc:
        assert "registered provider" in str(exc)
    else:
        raise AssertionError("Unregistered provider was accepted")


def test_dynamic_chat_provider_config_comes_from_catalog(monkeypatch):
    monkeypatch.setattr(
        catalog_service,
        "get_catalog",
        lambda capability=None: {
            "providers": [
                {
                    "id": "internal",
                    "label": "Internal gateway",
                    "base_url": "https://llm.example/v1",
                }
            ],
            "entries": [
                {
                    "provider": "internal",
                    "provider_label": "Internal gateway",
                    "capability": "chat",
                    "model": "internal-chat",
                    "model_display": "Internal Chat",
                    "base_url": "https://llm.example/v1",
                }
            ],
        },
    )

    config = llm_providers.get_provider_config("internal")

    assert config["base_url"] == "https://llm.example/v1"
    assert config["default_model"] == "internal-chat"
    assert config["models"] == [
        {"id": "internal-chat", "label": "Internal Chat"}
    ]


def test_add_provider_uses_preset_and_invalidates_provider_cache(monkeypatch):
    saved = {}
    invalidated = {"called": False}
    monkeypatch.setattr(
        catalog_service.model_provider_repository,
        "add",
        lambda provider: saved.update(provider),
    )
    monkeypatch.setattr(
        catalog_service,
        "invalidate_provider_cache",
        lambda: invalidated.__setitem__("called", True),
    )

    result = catalog_service.add_provider(
        {"preset_id": "cohere", "name": "Cohere"}
    )

    assert result["id"] == "cohere"
    assert result["base_url"] == "https://api.cohere.com/v2"
    assert saved == result
    assert invalidated["called"] is True


def test_unlisted_provider_id_is_generated_from_name(monkeypatch):
    monkeypatch.setattr(
        catalog_service.model_provider_repository,
        "add",
        lambda provider: None,
    )
    monkeypatch.setattr(catalog_service, "invalidate_provider_cache", lambda: None)

    result = catalog_service.add_provider(
        {"name": "My Internal Gateway", "base_url": "https://llm.example/v1"}
    )

    assert result["id"] == "my_internal_gateway"
    assert result["label"] == "My Internal Gateway"


def test_custom_provider_presets_are_ordered_last():
    presets = catalog_service.get_catalog()["provider_presets"]

    first_custom = next(index for index, item in enumerate(presets) if item["is_custom"])
    assert all(not item["is_custom"] for item in presets[:first_custom])
    assert all(item["is_custom"] for item in presets[first_custom:])
    assert presets[-1]["id"] == "custom"
