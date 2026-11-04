import asyncio

from app.core.database import get_connection
from app.modules.documents.processing_queue import document_processing_queue
from app.modules.documents.service import prepare_rechunk
from app.modules.embedding import service as embedding
from app.modules.evaluation import lab_repository, repository
from app.modules.evidence_validation import service as validation
from app.modules.reranking import service as reranking


async def publish(identifier):
    run = await asyncio.to_thread(repository.get, identifier)
    artifacts = await asyncio.to_thread(lab_repository.artifacts, identifier)
    if run["status"] != "completed" or "selected_parameters" not in artifacts:
        raise ValueError("A completed parameter experiment is required.")
    index = artifacts["selected_index"]["stats"]
    params = artifacts["selected_parameters"]["parameters"]
    if index["chunker"] != "production-paragraph-v3-exact-budget":
        raise ValueError("Obsolete chunker experiment; rerun exact-budget experiments first.")
    if index["max_chunk_tokens"] > index["budget"]:
        raise ValueError("The experiment violated its token budget; do not publish it.")

    def configure():
        from app.modules.evaluation.experiments import source_fingerprint, sources

        with get_connection() as conn:
            if conn.execute(
                "SELECT 1 FROM document_tasks WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone():
                raise ValueError("Wait for active document tasks to finish before publishing.")
            cached = conn.execute(
                "SELECT source_snapshot,status FROM evaluation_indexes WHERE id=%s",
                (artifacts["selected_index"]["index_id"],),
            ).fetchone()
        if not cached or cached["status"] != "ready":
            raise ValueError("The selected experiment index is unavailable.")
        if cached["source_snapshot"] != source_fingerprint(sources()):
            raise ValueError("Test source content changed; rerun the experiment before publishing.")
        if embedding.active_model_id() != "Qwen/Qwen3-Embedding-0.6B":
            raise ValueError("Select the tested Qwen embedding model before publishing.")
        embedding.update_config(
            {
                "chunk_token_budget": index["budget"],
                "chunk_overlap_tokens": index["overlap"],
                "context_header_strategy": "none",
                "evidence_distance_threshold": params["distance"],
            }
        )
        reranking.update_config(
            {
                "enabled": True,
                "provider": "local",
                "local_model": "Qwen/Qwen3-Reranker-0.6B",
                "min_score": params["floor"],
            }
        )
        validation.save_config(
            {
                "enabled": True,
                "decompose": True,
                "per_document_quota": params["per_document_quota"],
                "candidate_pool_size": 36,
                "default_top_k": params["top_k"],
            }
        )
        # Re-split stored text; a full rescan would call the metadata LLM per document.
        return prepare_rechunk()

    identifiers = await asyncio.to_thread(configure)
    task_ids = []
    for document_id in identifiers:
        state = await document_processing_queue.enqueue(document_id, "rechunk")
        task_ids.append(str(state.task["id"]))
    # Keep the existing evaluation generation model, but default Top-K to the measured choice.
    config = service_settings_with_top_k(params["top_k"])
    return {
        "queued": len(task_ids),
        "task_ids": task_ids,
        "parameters": params,
        "chunking": {"budget": index["budget"], "overlap": index["overlap"]},
        "evaluation_settings": config,
    }


def service_settings_with_top_k(k):
    from app.modules.evaluation import service

    current = service.settings().model_copy(update={"top_k": k})
    service.save_settings(current)
    return current.model_dump()
