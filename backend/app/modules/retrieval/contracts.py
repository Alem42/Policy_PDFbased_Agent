from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RetrievalScope = Literal["selected", "full_corpus"]


@dataclass(frozen=True)
class RetrievalRequest:
    """Provider-independent request for knowledge-base evidence."""

    question: str
    scope: RetrievalScope = "selected"
    identifiers: tuple[str, ...] = ()
    top_k: int = 8
    include_restricted: bool = False


@dataclass(frozen=True)
class EvidenceDecision:
    sufficient: bool
    reason: str | None = None


@dataclass
class RetrievalResult:
    """Complete output needed by answer writers and Agent tools."""

    pages: list[dict] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)
    raw_chunks: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    context: str = ""
    truncated: bool = False
    used_vector_retrieval: bool = False
    evidence: EvidenceDecision = field(default_factory=lambda: EvidenceDecision(False))

    def as_state(self) -> dict:
        """Return compatibility keys consumed by existing LangGraph state."""

        return {
            "pages": self.pages,
            "chunks": self.chunks,
            "raw_chunks": self.raw_chunks,
            "citations": self.citations,
            "context": self.context,
            "truncated": self.truncated,
            "used_vector_retrieval": self.used_vector_retrieval,
            "evidence_sufficient": self.evidence.sufficient,
            "evidence_reason": self.evidence.reason,
        }
