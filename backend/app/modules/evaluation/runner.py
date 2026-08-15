"""Concurrent, deterministic runner for the framework-independent search capability."""

from __future__ import annotations

import asyncio
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.modules.chat.capabilities import PolicySearchCapability, PolicySearchRequest
from app.modules.evaluation.contracts import (
    EVAL_SCHEMA_VERSION,
    EvalCase,
    EvalCaseResult,
    ExperimentResult,
)
from app.modules.retrieval.contracts import RetrievalResult


async def run_experiment(
    cases: list[EvalCase],
    capability: PolicySearchCapability,
    *,
    dataset_path: str | Path,
    max_concurrency: int = 1,
    experiment_id: str | None = None,
) -> ExperimentResult:
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1.")

    resolved_experiment_id = experiment_id or str(uuid4())
    started_at = datetime.now(UTC)
    semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(case: EvalCase) -> EvalCaseResult:
        async with semaphore:
            return await _run_case(case, capability, resolved_experiment_id)

    results = tuple(await asyncio.gather(*(execute(case) for case in cases)))
    finished_at = datetime.now(UTC)
    passed_count = sum(result.passed for result in results)
    latencies = [result.latency_ms for result in results]
    return ExperimentResult(
        schema_version=EVAL_SCHEMA_VERSION,
        experiment_id=resolved_experiment_id,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        dataset_path=str(dataset_path),
        case_count=len(results),
        passed_count=passed_count,
        pass_rate=passed_count / len(results) if results else 0.0,
        mean_latency_ms=round(statistics.fmean(latencies), 3) if latencies else 0.0,
        results=results,
    )


async def _run_case(
    case: EvalCase,
    capability: PolicySearchCapability,
    experiment_id: str,
) -> EvalCaseResult:
    run_id = f"eval:{experiment_id}:{case.case_id}"
    started_at = time.perf_counter()
    try:
        result = await asyncio.to_thread(
            capability.search,
            PolicySearchRequest(
                query=case.query,
                scope=case.scope,
                identifiers=case.identifiers,
                top_k=case.top_k,
                metadata_filters=case.metadata_filters,
            ),
        )
    except Exception as exc:
        return EvalCaseResult(
            case_id=case.case_id,
            category=case.category,
            run_id=run_id,
            passed=False,
            evidence_expected=case.expected_evidence,
            evidence_actual=None,
            evidence_match=False,
            citation_count=0,
            citation_requirement_met=False,
            expected_sources_matched=False,
            citation_quality=0.0,
            latency_ms=_elapsed_ms(started_at),
            tool_trace=("policy_search",),
            error_type=type(exc).__name__,
        )
    return _score_case(case, result, run_id, _elapsed_ms(started_at))


def _score_case(
    case: EvalCase,
    result: RetrievalResult,
    run_id: str,
    latency_ms: float,
) -> EvalCaseResult:
    citation_count = len(result.citations)
    evidence_actual = result.evidence.sufficient
    evidence_match = evidence_actual == case.expected_evidence
    citation_requirement_met = citation_count >= case.minimum_citations
    searchable_sources = " ".join(
        str(citation.get(key, ""))
        for citation in result.citations
        for key in ("title", "filename", "document_id", "source_url")
    ).casefold()
    expected_sources_matched = all(
        expected.casefold() in searchable_sources
        for expected in case.expected_source_contains
    )
    citation_quality = _citation_quality(result.citations)
    passed = evidence_match and citation_requirement_met and expected_sources_matched
    return EvalCaseResult(
        case_id=case.case_id,
        category=case.category,
        run_id=run_id,
        passed=passed,
        evidence_expected=case.expected_evidence,
        evidence_actual=evidence_actual,
        evidence_match=evidence_match,
        citation_count=citation_count,
        citation_requirement_met=citation_requirement_met,
        expected_sources_matched=expected_sources_matched,
        citation_quality=citation_quality,
        latency_ms=latency_ms,
        tool_trace=("policy_search",),
    )


def _citation_quality(citations: list[dict]) -> float:
    if not citations:
        return 0.0
    complete = sum(
        bool(citation.get("quote"))
        and any(
            citation.get(key)
            for key in ("title", "filename", "document_id", "source_url")
        )
        for citation in citations
    )
    return round(complete / len(citations), 3)


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)
