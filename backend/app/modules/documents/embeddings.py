"""Backward-compatible shim.

The real embedding logic now lives in `app.modules.embedding` (one package,
one source of truth). This module only re-exports the names the rest of the
codebase (and tests/scripts) still import, delegating to the package. New code
should import `app.modules.embedding.service` directly.
"""

from __future__ import annotations

from app.modules.embedding import service as _embedding
from app.modules.embedding.settings import DEFAULT_LOCAL_MODEL
from app.modules.embedding.tokens import _tiktoken_count

# Public embedding API (unchanged signatures).
EMBEDDING_MODEL_NAME = DEFAULT_LOCAL_MODEL
embed_documents = _embedding.embed_documents
embed_queries = _embedding.embed_queries
embed_query = _embedding.embed_query
vector_literal = _embedding.vector_literal


def get_embedding_model_name() -> str:
    """Identifier of the active embedding model (stored on each chunk row)."""
    return _embedding.active_model_id()


def estimate_embedding_token_count(text: str) -> int:
    """Config-aware token count used for chunk sizing (model tokenizer or tiktoken)."""
    return _embedding.count_tokens(text)


def estimate_token_count(text: str) -> int:
    """Plain cl100k_base token estimate (legacy helper)."""
    return _tiktoken_count(text)
