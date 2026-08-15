"""Framework-independent inputs for chat capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.modules.retrieval.contracts import MetadataFilters, RetrievalRequest

PolicySearchScope = Literal["selected", "library"]


@dataclass(frozen=True)
class PolicySearchRequest:
    """A stable policy-search request shared by Agent, eval, and MCP adapters."""

    query: str
    scope: PolicySearchScope
    identifiers: tuple[str, ...] = ()
    top_k: int = 8
    include_restricted: bool = False
    metadata_filters: MetadataFilters = field(default_factory=MetadataFilters)

    def as_retrieval_request(self) -> RetrievalRequest:
        """Translate the application vocabulary to the retrieval domain."""

        retrieval_scope = "selected" if self.scope == "selected" else "full_corpus"
        return RetrievalRequest(
            question=self.query,
            scope=retrieval_scope,
            identifiers=self.identifiers,
            top_k=self.top_k,
            include_restricted=self.include_restricted,
            metadata_filters=self.metadata_filters,
        )
