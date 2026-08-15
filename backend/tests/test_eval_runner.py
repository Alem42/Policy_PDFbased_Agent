from __future__ import annotations

import json
from pathlib import Path

from app.modules.evaluation.contracts import EvalCase
from app.modules.evaluation.reporting import write_experiment_reports
from app.modules.evaluation.runner import run_experiment
from app.modules.retrieval.contracts import EvidenceDecision, RetrievalResult


class FakeCapability:
    def search(self, request):
        if "missing" in request.query:
            return RetrievalResult(evidence=EvidenceDecision(False, "unsupported"))
        if "error" in request.query:
            raise RuntimeError("retriever unavailable")
        return RetrievalResult(
            citations=[
                {
                    "title": "Australia Responsible AI Policy",
                    "document_id": "doc-1",
                    "quote": "Grounded evidence",
                }
            ],
            evidence=EvidenceDecision(True, "supported"),
        )


async def test_runner_scores_cases_and_preserves_dataset_order() -> None:
    cases = [
        EvalCase(
            case_id="supported",
            category="selected_retrieval",
            query="supported",
            scope="selected",
            identifiers=("doc-1",),
            expected_source_contains=("Australia",),
        ),
        EvalCase(
            case_id="missing",
            category="insufficient_evidence",
            query="missing",
            scope="selected",
            identifiers=("doc-1",),
            expected_evidence=False,
            minimum_citations=0,
        ),
        EvalCase(
            case_id="error",
            category="library_retrieval",
            query="error",
            scope="library",
        ),
    ]

    experiment = await run_experiment(
        cases,
        FakeCapability(),
        dataset_path="cases.jsonl",
        max_concurrency=3,
        experiment_id="experiment-1",
    )

    assert [result.case_id for result in experiment.results] == [
        "supported",
        "missing",
        "error",
    ]
    assert [result.passed for result in experiment.results] == [True, True, False]
    assert experiment.passed_count == 2
    assert experiment.pass_rate == 2 / 3
    assert experiment.results[0].citation_quality == 1.0
    assert experiment.results[2].error_type == "RuntimeError"
    assert all(result.tool_trace == ("policy_search",) for result in experiment.results)


async def test_reporter_writes_json_and_markdown_tables(tmp_path: Path) -> None:
    case = EvalCase(
        case_id="supported",
        category="selected_retrieval",
        query="supported",
        scope="selected",
        identifiers=("doc-1",),
        expected_source_contains=("Australia",),
    )
    experiment = await run_experiment(
        [case],
        FakeCapability(),
        dataset_path="cases.jsonl",
        experiment_id="experiment-1",
    )

    json_path, markdown_path = write_experiment_reports(experiment, tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["schema_version"] == "policy-search-eval-v1"
    assert payload["results"][0]["run_id"].endswith(":supported")
    assert "| supported | selected_retrieval | PASS |" in markdown


async def test_runner_rejects_invalid_concurrency() -> None:
    try:
        await run_experiment([], FakeCapability(), dataset_path="cases.jsonl", max_concurrency=0)
    except ValueError as exc:
        assert "max_concurrency" in str(exc)
    else:
        raise AssertionError("Expected invalid concurrency to fail")
