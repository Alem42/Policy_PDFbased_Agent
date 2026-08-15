"""Versioned, provider-neutral contracts for reproducible evaluations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.modules.chat.capabilities.contracts import PolicySearchScope
from app.modules.retrieval.contracts import MetadataFilters

EVAL_SCHEMA_VERSION = "policy-search-eval-v1"
EvalCategory = Literal[
    "selected_retrieval",
    "library_retrieval",
    "metadata_filter",
    "insufficient_evidence",
]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: EvalCategory
    query: str
    scope: PolicySearchScope
    identifiers: tuple[str, ...] = ()
    expected_evidence: bool = True
    expected_source_contains: tuple[str, ...] = ()
    minimum_citations: int = 1
    top_k: int = 8
    metadata_filters: MetadataFilters = field(default_factory=MetadataFilters)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> EvalCase:
        return cls(
            case_id=str(value["case_id"]),
            category=value["category"],
            query=str(value["query"]),
            scope=value["scope"],
            identifiers=tuple(value.get("identifiers") or ()),
            expected_evidence=bool(value.get("expected_evidence", True)),
            expected_source_contains=tuple(value.get("expected_source_contains") or ()),
            minimum_citations=int(value.get("minimum_citations", 1)),
            top_k=int(value.get("top_k", 8)),
            metadata_filters=MetadataFilters.from_mapping(value.get("metadata_filters")),
        )


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    category: EvalCategory
    run_id: str
    passed: bool
    evidence_expected: bool
    evidence_actual: bool | None
    evidence_match: bool
    citation_count: int
    citation_requirement_met: bool
    expected_sources_matched: bool
    citation_quality: float
    latency_ms: float
    tool_trace: tuple[str, ...]
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentResult:
    schema_version: str
    experiment_id: str
    started_at: str
    finished_at: str
    dataset_path: str
    case_count: int
    passed_count: int
    pass_rate: float
    mean_latency_ms: float
    results: tuple[EvalCaseResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
