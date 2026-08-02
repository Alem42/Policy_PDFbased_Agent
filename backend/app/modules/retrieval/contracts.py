from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RetrievalScope = Literal["selected", "full_corpus"]


@dataclass(frozen=True)
class MetadataFilters:
    """Conservative, exact-match document metadata constraints."""

    policy_areas: tuple[str, ...] = ()
    country_regions: tuple[str, ...] = ()
    source_organisations: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    year_from: int | None = None
    year_to: int | None = None
    freshness_requested: bool = False

    @property
    def active(self) -> bool:
        return any(
            (
                self.policy_areas,
                self.country_regions,
                self.source_organisations,
                self.languages,
                self.tags,
                self.year_from is not None,
                self.year_to is not None,
                self.freshness_requested,
            )
        )

    def as_dict(self) -> dict:
        return {
            "policy_areas": list(self.policy_areas),
            "country_regions": list(self.country_regions),
            "source_organisations": list(self.source_organisations),
            "languages": list(self.languages),
            "tags": list(self.tags),
            "year_from": self.year_from,
            "year_to": self.year_to,
            "freshness_requested": self.freshness_requested,
        }

    @classmethod
    def from_mapping(cls, value: dict | None) -> MetadataFilters:
        value = value or {}
        return cls(
            policy_areas=tuple(value.get("policy_areas") or ()),
            country_regions=tuple(value.get("country_regions") or ()),
            source_organisations=tuple(value.get("source_organisations") or ()),
            languages=tuple(value.get("languages") or ()),
            tags=tuple(value.get("tags") or ()),
            year_from=value.get("year_from"),
            year_to=value.get("year_to"),
            freshness_requested=bool(value.get("freshness_requested", False)),
        )


@dataclass(frozen=True)
class RetrievalRequest:
    """Provider-independent request for knowledge-base evidence."""

    question: str
    scope: RetrievalScope = "selected"
    identifiers: tuple[str, ...] = ()
    top_k: int = 8
    include_restricted: bool = False
    metadata_filters: MetadataFilters = field(default_factory=MetadataFilters)


@dataclass(frozen=True)
class QuestionValidationRequest:
    """Batch-check candidate questions against selected documents."""

    questions: tuple[str, ...]
    identifiers: tuple[str, ...]
    top_k: int = 5
    max_results: int = 3
    include_restricted: bool = False
    max_distance: float | None = None
    use_reranker: bool = True


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
    filter_applied: bool = False
    filter_fallback: bool = False
    filter_notice: str | None = None

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
            "filter_applied": self.filter_applied,
            "filter_fallback": self.filter_fallback,
            "filter_notice": self.filter_notice,
        }
