"""Download/probe both Qwen models without exposing API credentials."""
import json
import time

from app.modules.embedding.providers import QwenEmbeddingProvider
from app.modules.embedding.settings import EmbeddingConfig
from app.modules.local_models.runtime import EMBEDDING_MODEL, RERANKER_MODEL, local_model_runtime


def main():
    started = time.perf_counter()
    try:
        provider = QwenEmbeddingProvider(EmbeddingConfig(
            provider="local", local_model=EMBEDDING_MODEL, dimensions=1024, local_idle_seconds=300,
        ))
        vectors = provider.embed_documents(["Paris is the capital of France.", "Bananas are yellow."])
        query = provider.embed_queries(["What is the capital of France?"])[0]
        scores = local_model_runtime.call(
            "rerank", model=RERANKER_MODEL, query="What is the capital of France?",
            texts=["Paris is the capital of France.", "Bananas are yellow."], idle_seconds=300,
            instruction="Given a question, retrieve passages that answer the question.",
        )
        print(json.dumps({"dimension": len(query), "norm": sum(x*x for x in query)**0.5,
                          "cosines": [sum(x*y for x,y in zip(query,v)) for v in vectors],
                          "reranker_scores": scores, "runtime": local_model_runtime.status(),
                          "elapsed_seconds": round(time.perf_counter()-started, 2)}, indent=2), flush=True)
    finally:
        local_model_runtime.unload()
    print(json.dumps({"after_unload": local_model_runtime.status()}), flush=True)


if __name__ == "__main__":
    main()
