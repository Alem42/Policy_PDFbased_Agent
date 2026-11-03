import pytest

from app.core import environment
from app.modules.embedding.settings import EmbeddingConfig
from app.modules.local_models import preload
from app.modules.local_models.runtime import EMBEDDING_MODEL, RERANKER_MODEL
from app.modules.reranking.config import RerankingConfig


def use_venvs(monkeypatch, tmp_path, *names):
    paths = []
    for name in names:
        path = tmp_path / name / ".venv"
        path.mkdir(parents=True)
        paths.append(path)
    monkeypatch.setattr(environment, "PROJECT_VENVS", tuple(paths) or (tmp_path / "none",))
    monkeypatch.setattr(environment.get_settings(), "require_project_venv", True)
    return paths


def test_foreign_interpreter_is_refused_with_start_command(monkeypatch, tmp_path):
    use_venvs(monkeypatch, tmp_path, "repo")
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / "system-python"))
    with pytest.raises(RuntimeError) as caught:
        environment.require_project_interpreter()
    assert "scripts.run_backend" in str(caught.value)


def test_project_interpreter_and_venvless_installs_are_allowed(monkeypatch, tmp_path):
    (venv,) = use_venvs(monkeypatch, tmp_path, "repo")
    monkeypatch.setattr(environment.sys, "prefix", str(venv))
    environment.require_project_interpreter()
    use_venvs(monkeypatch, tmp_path / "container")
    monkeypatch.setattr(environment.sys, "prefix", "/usr/local")
    environment.require_project_interpreter()


def test_guard_can_be_disabled(monkeypatch, tmp_path):
    use_venvs(monkeypatch, tmp_path, "repo")
    monkeypatch.setattr(environment.get_settings(), "require_project_venv", False)
    monkeypatch.setattr(environment.sys, "prefix", str(tmp_path / "other"))
    environment.require_project_interpreter()


@pytest.mark.parametrize(
    ("embedding", "reranking", "expected"),
    [
        (
            EmbeddingConfig(local_model=EMBEDDING_MODEL),
            RerankingConfig(local_model=RERANKER_MODEL),
            [("embed", EMBEDDING_MODEL), ("rerank", RERANKER_MODEL)],
        ),
        (EmbeddingConfig(), RerankingConfig(local_model=RERANKER_MODEL, enabled=False), []),
        (EmbeddingConfig(provider="api", local_model=EMBEDDING_MODEL), RerankingConfig(), []),
    ],
)
def test_only_selected_local_qwen_models_are_preloaded(monkeypatch, embedding, reranking, expected):
    from app.modules.embedding import service as embedding_service
    from app.modules.reranking import service as reranking_service

    monkeypatch.setattr(embedding_service, "active_config", lambda: embedding)
    monkeypatch.setattr(reranking_service, "active_config", lambda: reranking)
    assert preload.selected_local_models() == expected


def test_preload_failure_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(preload.get_settings(), "database_enabled", True)
    monkeypatch.setattr(preload.get_settings(), "local_models_preload", True)
    monkeypatch.setattr(preload, "selected_local_models", lambda: [("embed", EMBEDDING_MODEL)])

    def broken(_):
        raise RuntimeError("Local Qwen dependencies missing: torch")

    monkeypatch.setattr(preload.local_model_runtime, "preload", broken)
    preload.preload_selected_models()
    assert "preload failed" in caplog.text
