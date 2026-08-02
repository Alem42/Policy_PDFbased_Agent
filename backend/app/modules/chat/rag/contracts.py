"""Compatibility exports for the former unused RAG contracts module."""

from app.modules.retrieval.contracts import (
    EvidenceDecision,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScope,
)

__all__ = ["EvidenceDecision", "RetrievalRequest", "RetrievalResult", "RetrievalScope"]
