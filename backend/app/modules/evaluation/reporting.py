"""Machine-readable and reviewer-friendly experiment result writers."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.evaluation.contracts import ExperimentResult


def write_experiment_reports(
    experiment: ExperimentResult,
    output_directory: str | Path,
) -> tuple[Path, Path]:
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    stem = f"policy-search-{experiment.experiment_id}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    json_path.write_text(
        json.dumps(experiment.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_as_markdown(experiment), encoding="utf-8")
    return json_path, markdown_path


def _as_markdown(experiment: ExperimentResult) -> str:
    lines = [
        "# Policy Search Evaluation",
        "",
        f"- Experiment: `{experiment.experiment_id}`",
        f"- Dataset: `{experiment.dataset_path}`",
        f"- Passed: `{experiment.passed_count}/{experiment.case_count}`",
        f"- Pass rate: `{experiment.pass_rate:.1%}`",
        f"- Mean latency: `{experiment.mean_latency_ms:.3f} ms`",
        "",
        "| Case | Category | Pass | Evidence | Citations | Citation quality | Latency ms | Error |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in experiment.results:
        evidence = f"{result.evidence_actual}/{result.evidence_expected}"
        lines.append(
            f"| {result.case_id} | {result.category} | "
            f"{'PASS' if result.passed else 'FAIL'} | {evidence} | "
            f"{result.citation_count} | {result.citation_quality:.1%} | "
            f"{result.latency_ms:.3f} | {result.error_type or ''} |"
        )
    lines.append("")
    return "\n".join(lines)
