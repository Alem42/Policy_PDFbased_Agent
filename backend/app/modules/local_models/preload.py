"""Bring the selected local Qwen models into memory before the first request needs them."""

import logging
from threading import Thread

from app.core.config import get_settings
from app.modules.local_models.runtime import EMBEDDING_MODEL, RERANKER_MODEL, local_model_runtime

logger = logging.getLogger(__name__)


def selected_local_models() -> list[tuple[str, str]]:
    from app.modules.embedding import service as embedding
    from app.modules.reranking import service as reranking

    models = []
    config = embedding.active_config()
    if config.provider == "local" and config.local_model == EMBEDDING_MODEL:
        models.append(("embed", EMBEDDING_MODEL))
    config = reranking.active_config()
    if config.enabled and config.provider == "local" and config.local_model == RERANKER_MODEL:
        models.append(("rerank", RERANKER_MODEL))
    return models


def preload_selected_models() -> None:
    settings = get_settings()
    if not settings.local_models_preload or not settings.database_enabled:
        return
    try:
        models = selected_local_models()
        if models:
            local_model_runtime.preload(models)
            status = local_model_runtime.status()
            logger.warning(
                "Local models loaded: %s on %s (%.0f MiB)",
                ", ".join(name for _, name in models),
                status.get("device", "?"),
                status.get("allocated_bytes", 0) / 2**20,
            )
    except Exception:
        logger.exception("Local model preload failed; requests that need these models will fail")


def refresh_selected_models() -> None:
    """After a model switch, free the previous weights and load the new selection."""

    def run():
        local_model_runtime.unload()
        preload_selected_models()

    Thread(target=run, name="local-model-refresh", daemon=True).start()
