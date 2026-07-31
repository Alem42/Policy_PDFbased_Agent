"""Embedding providers behind one interface.

Two providers implement the same shape so the app can switch between them:
  - LocalFastembedProvider: on-box ONNX model via fastembed (no network).
      Asymmetric: separate query/passage encodings. Ships its own tokenizer.
  - OpenAICompatibleProvider: any OpenAI-compatible /embeddings endpoint
      (Zhipu, OpenAI, ...). Symmetric: one encoding for everything. No local
      tokenizer, so token counting falls back to tiktoken (see tokens.py).

Every method returns plain python floats; dimension is validated centrally so a
misconfigured model fails loudly instead of writing bad vectors (the
local-hashing-v1 lesson: never mix vectors from different models).
"""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from app.core.config import get_settings, resolve_backend_path
from app.modules.embedding.settings import EmbeddingConfig

# model may return many types of values, so we convert to list[float]
def _embeddings_url(base_url: str) -> str:
    """Normalise any Zhipu/OpenAI base to the single /embeddings endpoint.

    Accepts '.../v4', '.../v4/', '.../v4/embeddings' or trailing slash variants
    and always returns '.../v4/embeddings' — avoids the /embeddings/embeddings 404.
    """
    base = base_url.rstrip("/")
    if base.endswith("/embeddings"):
        base = base[: -len("/embeddings")]
    return f"{base}/embeddings"


def _vector_to_list(vector, expected_dim: int) -> list[float]:
    values = [float(v) for v in vector]
    if len(values) != expected_dim:
        raise ValueError(f"Embedding dimension mismatch: expected {expected_dim}, got {len(values)}.")
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Embedding contains a non-finite value.")
    return values


class EmbeddingProvider(ABC):
    """Common contract every provider satisfies."""

    dimension: int
    model_id: str
    is_symmetric: bool

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Passage-mode vectors for stored chunks."""

    @abstractmethod
    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        """Query-mode vectors for one or more user questions, preserving order."""

    def embed_query(self, text: str) -> list[float]:
        """Compatibility wrapper for callers that have a single question."""
        return self.embed_queries([text])[0]

    def count_tokens(self, text: str) -> int | None:
        """Exact token count if the provider has a tokenizer, else None (caller approximates)."""
        return None


# ── Local (fastembed) ───────────────────────────────────────────────────────

# lazy loading of fastembed model/tokenizer to avoid import errors when the package is not installed
@lru_cache(maxsize=4)
def _load_fastembed_model(model_name: str):
    from fastembed import TextEmbedding

    cache_dir = resolve_backend_path(get_settings().model_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))


@lru_cache(maxsize=4)
def _load_fastembed_tokenizer(model_name: str):
    from fastembed.common.preprocessor_utils import load_tokenizer

    model = _load_fastembed_model(model_name)
    tokenizer, _ = load_tokenizer(model_dir=model.model._model_dir)
    tokenizer.no_truncation()
    return tokenizer


class LocalFastembedProvider(EmbeddingProvider):
    is_symmetric = False

    def __init__(self, config: EmbeddingConfig) -> None:
        self.model_id = config.local_model
        self.dimension = config.active_dimension()
        self._batch_size = config.batch_size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        cleaned = [t.strip() for t in texts]
        if any(not t for t in cleaned):
            raise ValueError("Document text must not be blank.")
        model = _load_fastembed_model(self.model_id)
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), self._batch_size):
            batch = cleaned[start : start + self._batch_size]
            vectors.extend(_vector_to_list(v, self.dimension) for v in model.passage_embed(batch))
        return vectors

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise ValueError("Query text must not be blank.")
        model = _load_fastembed_model(self.model_id)
        vectors = list(model.query_embed(cleaned))
        if len(vectors) != len(cleaned):
            raise RuntimeError("Embedding provider returned a different number of query vectors.")
        return [_vector_to_list(vector, self.dimension) for vector in vectors]

    def count_tokens(self, text: str) -> int | None:
        # bge's max sequence length is close to our chunk budget, so exactness matters.
        return max(1, len(_load_fastembed_tokenizer(self.model_id).encode(text).ids))


# ── API (OpenAI-compatible, e.g. Zhipu) ─────────────────────────────────────


class OpenAICompatibleProvider(EmbeddingProvider):
    is_symmetric = True

    def __init__(self, config: EmbeddingConfig) -> None:
        self.model_id = config.api_model
        self.dimension = config.dimensions
        self._base_url = config.api_base_url.rstrip("/")
        self._api_key = config.api_key
        self._batch_size = config.batch_size
        # Only send `dimensions` when the model supports variable dims (Zhipu embedding-3).
        self._send_dimensions = not config.auto_detect_dimensions

    def _post(self, inputs: list[str]) -> list[list[float]]:
        if ( not self._base_url 
           or not self._api_key 
           or not self.model_id ) :
            raise ValueError("API embedding provider is missing base_url, api_key, or model.")
        payload: dict = {"model": self.model_id, "input": inputs}
        if self._send_dimensions:
            payload["dimensions"] = self.dimension
        response = httpx.post(
            _embeddings_url(self._base_url),
            headers={
                "Authorization": f"Bearer {self._api_key}"
                },
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda d: d.get("index", 0))]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        cleaned = [t.strip() for t in texts]
        if any(not t for t in cleaned):
            raise ValueError("Document text must not be blank.")
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), self._batch_size):
            batch = cleaned[start : start + self._batch_size]
            vectors.extend(_vector_to_list(v, self.dimension) for v in self._post(batch))
        return vectors

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts]
        if not cleaned:
            return []
        if any(not text for text in cleaned):
            raise ValueError("Query text must not be blank.")
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), self._batch_size):
            batch = cleaned[start : start + self._batch_size]
            vectors.extend(_vector_to_list(vector, self.dimension) for vector in self._post(batch))
        if len(vectors) != len(cleaned):
            raise RuntimeError("Embedding provider returned a different number of query vectors.")
        return vectors

# test connection probe (used by the admin UI) to verify connectivity and report the real dimension
def probe(config: EmbeddingConfig) -> dict:
    """Embed one probe string to verify connectivity and report the real dimension.

    Used by the admin "Test connection" button. Bypasses the strict dimension
    check (that is what we are trying to discover).
    """
    started = time.perf_counter()
    if config.provider == "local":
        model = _load_fastembed_model(config.local_model)
        vector = list(model.query_embed("connection test"))[0]
        dim = len(list(vector))
    else:
        payload: dict = {"model": config.api_model, "input": ["connection test"]}
        if not config.auto_detect_dimensions:
            payload["dimensions"] = config.dimensions
        response = httpx.post(
            _embeddings_url(config.api_base_url),
            headers={"Authorization": f"Bearer {config.api_key}"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        dim = len(body["data"][0]["embedding"])
    return {
        "model": config.active_model_id(),
        "dimension": dim,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
