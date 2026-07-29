"""Token counting used for chunk sizing.

Chunk sizing happens BEFORE any embedding call, so it needs a count we can
compute locally:
  - "model": the provider's own tokenizer (exact). Only local models have one.
  - "tiktoken": cl100k_base approximation (~10-20% off), fine when the model's
    input window is far larger than the chunk budget (e.g. API models).
  - "auto": model tokenizer if the provider exposes one, else tiktoken.

API models' response `usage.total_tokens` is exact but only known AFTER the
call, so it is used for billing/telemetry, never for pre-chunk sizing.
"""

from __future__ import annotations

from functools import lru_cache

from app.modules.embedding.providers import EmbeddingProvider
from app.modules.embedding.settings import EmbeddingConfig


@lru_cache(maxsize=1)
def _tiktoken_encoder():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def _tiktoken_count(text: str) -> int:
    return max(1, len(_tiktoken_encoder().encode(text)))


def count_tokens(text: str, config: EmbeddingConfig, provider: EmbeddingProvider) -> int:
    """Token count for `text` under the active config/provider."""
    if config.token_counting == "tiktoken":
        return _tiktoken_count(text)
    if config.token_counting in ("auto", "model"):
        exact = provider.count_tokens(text)
        if exact is not None:
            return exact
    # "model" requested but provider has no tokenizer, or "auto" on an API model.
    return _tiktoken_count(text)
