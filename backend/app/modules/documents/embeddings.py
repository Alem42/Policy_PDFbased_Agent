from __future__ import annotations

import hashlib
import math
import re

from app.core.config import get_settings

EMBEDDING_MODEL_NAME = "local-hashing-v1"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def estimate_token_count(text: str) -> int:
    return max(1, len(text) // 4)


def embed_text(text: str, dimensions: int | None = None) -> list[float]:
    """Create a deterministic local vector for development.

    This keeps the database/vector retrieval pipeline working before an external
    embedding provider is chosen. It is not a replacement for a production
    semantic embedding model.
    """
    selected_dimensions = dimensions or get_settings().default_embedding_dimensions
    vector = [0.0] * selected_dimensions
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % selected_dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
