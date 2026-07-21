from __future__ import annotations

import math
from collections.abc import Iterable
from functools import lru_cache

import tiktoken
from fastembed import TextEmbedding
from fastembed.common.preprocessor_utils import load_tokenizer
from tokenizers import Tokenizer

from app.core.config import get_settings, resolve_backend_path

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# cl100k_base is the BPE encoding used by GPT-4 and DeepSeek.
# Loaded once at module import time; subsequent calls are near-instant.
_tokenizer = tiktoken.get_encoding("cl100k_base")


def estimate_token_count(text: str) -> int:
    """Return the BPE token count for text using the cl100k_base encoding.

    Replaces the old len(text)//4 heuristic, which severely underestimated
    CJK text. Error vs. actual model token count is typically <5% for
    DeepSeek and GPT-4 class models.
    """
    return max(1, len(_tokenizer.encode(text)))


def get_embedding_model_name() -> str:
    return get_settings().embedding_model_name


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> TextEmbedding:
    """Load each configured embedding model once per backend process."""
    cache_dir = resolve_backend_path(get_settings().model_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))


@lru_cache(maxsize=4)
def _load_chunking_tokenizer(model_name: str) -> Tokenizer:
    """Load an untruncated tokenizer dedicated to model-aware chunk sizing."""
    embedding_model = _load_model(model_name)
    tokenizer, _ = load_tokenizer(model_dir=embedding_model.model._model_dir)
    tokenizer.no_truncation()
    return tokenizer


def estimate_embedding_token_count(text: str) -> int:
    """Count tokens with the configured embedding model's own tokenizer."""
    tokenizer = _load_chunking_tokenizer(get_settings().embedding_model_name)
    return max(1, len(tokenizer.encode(text).ids))


def _vector_to_list(vector: Iterable[float], expected_dimensions: int) -> list[float]:
    values = [float(value) for value in vector]
    if len(values) != expected_dimensions:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dimensions}, received {len(values)}."
        )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Embedding contains a non-finite value.")
    return values


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Generate passage embeddings for document chunks in bounded batches."""
    if not texts:
        return []

    cleaned_texts = [text.strip() for text in texts]
    if any(not text for text in cleaned_texts):
        raise ValueError("Document text must not be blank.")

    settings = get_settings()
    model = _load_model(settings.embedding_model_name)
    vectors: list[list[float]] = []

    for start in range(0, len(cleaned_texts), settings.embedding_batch_size):
        batch = cleaned_texts[start : start + settings.embedding_batch_size]
        vectors.extend(
            _vector_to_list(vector, settings.default_embedding_dimensions)
            for vector in model.passage_embed(batch)
        )

    if len(vectors) != len(cleaned_texts):
        raise RuntimeError(
            "Embedding provider returned an unexpected number of document vectors: "
            f"expected {len(cleaned_texts)}, received {len(vectors)}."
        )
    return vectors


def embed_query(text: str) -> list[float]:
    """Generate the retrieval embedding for a user query."""
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Query text must not be blank.")

    settings = get_settings()
    model = _load_model(settings.embedding_model_name)
    vectors = list(model.query_embed(cleaned_text))
    if len(vectors) != 1:
        raise RuntimeError(
            "Embedding provider returned an unexpected number of query vectors: "
            f"expected 1, received {len(vectors)}."
        )
    return _vector_to_list(vectors[0], settings.default_embedding_dimensions)


def embed_text(text: str, dimensions: int | None = None) -> list[float]:
    """Backward-compatible alias for callers that embed a query-like string."""
    configured_dimensions = get_settings().default_embedding_dimensions
    if dimensions is not None and dimensions != configured_dimensions:
        raise ValueError(
            "Custom embedding dimensions are no longer supported: "
            f"configured model outputs {configured_dimensions} dimensions."
        )
    return embed_query(text)


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
