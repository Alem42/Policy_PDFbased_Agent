from app.core.settings_store import SingleRowSettings
from app.modules.embedding import service as embedding
from app.modules.embedding.settings import EmbeddingConfig


def test_a_save_in_one_process_reaches_another(postgres_repository):
    api, worker = SingleRowSettings("embedding_settings"), SingleRowSettings("embedding_settings")
    api.save(EmbeddingConfig(local_model="BAAI/bge-small-en-v1.5").model_dump_json())
    assert worker.load()["local_model"] == "BAAI/bge-small-en-v1.5"
    assert worker.changed(0) is False

    api.save(EmbeddingConfig(local_model="Qwen/Qwen3-Embedding-0.6B").model_dump_json())

    assert worker.changed(3600) is False  # throttled: no query yet
    assert worker.changed(0) is True
    assert worker.load()["local_model"] == "Qwen/Qwen3-Embedding-0.6B"
    assert worker.changed(0) is False
    assert api.changed(0) is False  # the saver already holds the new version


def test_task_snapshot_rereads_a_switched_model(postgres_repository, monkeypatch):
    other_process = SingleRowSettings("embedding_settings")
    other_process.save(EmbeddingConfig().model_dump_json())
    monkeypatch.setattr(
        embedding.embedding_settings_repository, "_store", SingleRowSettings("embedding_settings")
    )
    embedding._cache.update(config=None, provider=None)
    assert embedding.active_model_id() == "BAAI/bge-small-en-v1.5"

    other_process.save(EmbeddingConfig(local_model="BAAI/bge-base-en-v1.5").model_dump_json())

    with embedding.snapshot():
        assert embedding.active_model_id() == "BAAI/bge-base-en-v1.5"
        assert embedding.active_vector_table() == "chunk_vectors_baai_bge_base_en_v1_5_768"
    embedding._cache.update(config=None, provider=None)
