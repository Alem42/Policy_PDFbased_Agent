from threading import Thread
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.modules.embedding.providers import QwenEmbeddingProvider
from app.modules.embedding.settings import EmbeddingConfig
from app.modules.local_models import runtime as runtime_module
from app.modules.local_models.runtime import (
    EMBEDDING_MODEL,
    QUERY_INSTRUCTION,
    RERANKER_MODEL,
    LocalModelRuntime,
    local_model_runtime,
)
from app.modules.reranking import service as reranking
from app.modules.reranking.config import RerankingConfig


@pytest.mark.parametrize("missing", [{"torch"}, {"transformers"}, {"torch", "transformers"}])
def test_missing_dependencies_fail_before_spawning_with_startup_guidance(monkeypatch, missing):
    monkeypatch.setattr(
        runtime_module, "find_spec", lambda name: None if name in missing else object()
    )
    context = Mock()
    runtime = LocalModelRuntime(context=context)

    with pytest.raises(RuntimeError) as caught:
        runtime.call("embed", texts=["question"], model=EMBEDDING_MODEL)

    message = str(caught.value)
    assert all(name in message for name in missing)
    assert runtime_module.sys.executable in message
    assert "python -m scripts.run_backend" in message
    context.Pipe.assert_not_called()
    context.Process.assert_not_called()
    assert runtime.status()["loaded"] is False


def test_token_counting_reports_the_same_environment_problem(monkeypatch):
    monkeypatch.setattr(runtime_module, "find_spec", lambda name: None)
    runtime_module.tokenizer.cache_clear()
    with pytest.raises(RuntimeError, match="Local Qwen dependencies missing: torch, transformers"):
        runtime_module.count_tokens("question")


def test_qwen_query_instruction_passage_asymmetry(monkeypatch):
    seen = []

    def call(operation, **payload):
        seen.append(payload)
        return [[0.1] * 1024 for _ in payload["texts"]]

    monkeypatch.setattr(local_model_runtime, "call", call)
    provider = QwenEmbeddingProvider(EmbeddingConfig(local_model=EMBEDDING_MODEL))
    provider.embed_documents(["Original source text"])
    provider.embed_queries(["  policy question  "])
    assert seen[0]["texts"] == ["Original source text"]
    assert seen[1]["texts"] == [f"Instruct: {QUERY_INSTRUCTION}\nQuery: policy question"]
    assert seen[0]["batch_size"] == 8
    assert provider.is_symmetric is False


@pytest.mark.parametrize("bad", [[[1.0] * 384], [[float("nan")] * 1024], []])
def test_qwen_rejects_invalid_vectors(monkeypatch, bad):
    monkeypatch.setattr(local_model_runtime, "call", lambda *a, **kw: bad)
    with pytest.raises((ValueError, RuntimeError)):
        QwenEmbeddingProvider(EmbeddingConfig(local_model=EMBEDDING_MODEL)).embed_query("question")


def test_empty_inputs_do_not_load_gpu(monkeypatch):
    call = Mock(side_effect=AssertionError("GPU must not load"))
    monkeypatch.setattr(local_model_runtime, "call", call)
    provider = QwenEmbeddingProvider(EmbeddingConfig(local_model=EMBEDDING_MODEL))
    assert provider.embed_queries([]) == []
    assert provider.embed_documents([]) == []
    with pytest.raises(ValueError):
        provider.embed_query(" ")
    with pytest.raises(ValueError):
        provider.embed_documents([" "])
    call.assert_not_called()


def test_qwen_rerank_orders_scores_without_mutating_chunks(monkeypatch):
    monkeypatch.setattr(
        reranking, "active_config", lambda: RerankingConfig(local_model=RERANKER_MODEL)
    )
    monkeypatch.setattr(local_model_runtime, "call", lambda *a, **kw: [0.1, 0.9])
    chunks = [{"text": "weak"}, {"text": "strong"}]
    result = reranking.rerank("question", chunks, limit=1)
    assert result == [{"text": "strong", "reranker_score": 0.9}]
    assert "reranker_score" not in chunks[1]


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_qwen_probability_threshold_bounds(score):
    with pytest.raises(ValidationError):
        RerankingConfig(local_model=RERANKER_MODEL, min_score=score)
    # BGE retains its distinct logit scale.
    assert RerankingConfig(min_score=-2).resolved_min_score() == -2


def test_qwen_dimensions_and_idle_bounds():
    assert EmbeddingConfig(local_model=EMBEDDING_MODEL).active_dimension() == 1024
    assert RerankingConfig(local_model=RERANKER_MODEL).resolved_min_score() == 0.5
    for config in (EmbeddingConfig, RerankingConfig):
        with pytest.raises(ValidationError):
            config(local_idle_seconds=-1)


def fake_runtime(response=None, poll=True):
    connection = Mock()
    connection.poll.return_value = poll
    connection.recv.return_value = response or {
        "ok": True,
        "result": [[1]],
        "status": {"device": "cuda"},
    }
    process = Mock(pid=123)
    process.is_alive.return_value = True
    runtime = LocalModelRuntime(timeout=0.01)

    def start():
        runtime._process, runtime._connection = process, connection

    runtime._start = start
    return runtime, connection, process


def test_unload_terminates_child_and_closes_pipe(monkeypatch):
    monkeypatch.setattr(runtime_module.get_settings(), "local_models_keep_loaded", False)
    runtime, connection, process = fake_runtime()
    assert runtime.call("embed", idle_seconds=0) == [[1]]
    process.terminate.assert_called_once()
    connection.close.assert_called_once()
    assert runtime.status()["loaded"] is False
    assert runtime.status()["allocated_bytes"] == 0


def test_timeout_discards_gpu_worker():
    runtime, connection, process = fake_runtime(poll=False)
    with pytest.raises(TimeoutError):
        runtime.call("embed", idle_seconds=100)
    process.terminate.assert_called_once()
    assert runtime.status()["loaded"] is False


def test_old_idle_timer_cannot_unload_new_request(monkeypatch):
    monkeypatch.setattr(runtime_module.get_settings(), "local_models_keep_loaded", False)
    runtime, _, process = fake_runtime()
    runtime.call("embed", idle_seconds=300)
    old = runtime._generation
    runtime.call("embed", idle_seconds=300)
    runtime._expire(old)
    process.terminate.assert_not_called()
    runtime._expire(runtime._generation)
    process.terminate.assert_called_once()


def test_status_does_not_wait_for_a_busy_gpu_worker():
    runtime, _, _ = fake_runtime()
    results = []
    with runtime._lock:
        thread = Thread(target=lambda: results.append(runtime.status()))
        thread.start()
        thread.join(timeout=1)
        assert not thread.is_alive()
        assert results[0]["busy"] is True


def test_keep_loaded_ignores_idle_release(monkeypatch):
    monkeypatch.setattr(runtime_module.get_settings(), "local_models_keep_loaded", True)
    runtime, _, process = fake_runtime()
    runtime.call("embed", idle_seconds=0)
    assert runtime._timer is None
    process.terminate.assert_not_called()
    runtime.unload()
    process.terminate.assert_called_once()


def test_preload_loads_each_model_without_inference(monkeypatch):
    monkeypatch.setattr(runtime_module.get_settings(), "local_models_keep_loaded", True)
    runtime, connection, _ = fake_runtime({"ok": True, "result": [], "status": {}})
    runtime.preload([("embed", EMBEDDING_MODEL), ("rerank", RERANKER_MODEL)])
    sent = [call.args[0] for call in connection.send.call_args_list]
    assert sent == [
        {"operation": "load", "model": EMBEDDING_MODEL, "kind": "embed", "texts": []},
        {"operation": "load", "model": RERANKER_MODEL, "kind": "rerank", "texts": []},
    ]
