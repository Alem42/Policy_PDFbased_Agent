"""Strict JSONL loading for version-controlled evaluation cases."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.evaluation.contracts import EvalCase


def load_eval_cases(path: str | Path) -> list[EvalCase]:
    dataset_path = Path(path)
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = EvalCase.from_mapping(json.loads(line))
        except Exception as exc:
            raise ValueError(f"Invalid eval case at {dataset_path}:{line_number}: {exc}") from exc
        if case.case_id in seen_ids:
            raise ValueError(f"Duplicate eval case_id {case.case_id!r} at line {line_number}.")
        _validate_case(case, line_number)
        seen_ids.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError(f"Evaluation dataset is empty: {dataset_path}")
    return cases


def _validate_case(case: EvalCase, line_number: int) -> None:
    if not case.case_id.strip() or not case.query.strip():
        raise ValueError(f"case_id and query are required at line {line_number}.")
    if case.scope == "selected" and not case.identifiers:
        raise ValueError(f"Selected-scope case requires identifiers at line {line_number}.")
    if case.minimum_citations < 0:
        raise ValueError(f"minimum_citations cannot be negative at line {line_number}.")
    if not case.expected_evidence and case.minimum_citations != 0:
        raise ValueError(
            f"Insufficient-evidence case must set minimum_citations=0 at line {line_number}."
        )
