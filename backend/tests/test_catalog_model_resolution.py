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
