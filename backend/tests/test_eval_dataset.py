from pathlib import Path

import pytest

from app.modules.evaluation.dataset import load_eval_cases

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_smoke_dataset_has_unique_coverage_cases() -> None:
    cases = load_eval_cases(BACKEND_ROOT / "evals/smoke_policy_search.jsonl")

    assert len(cases) == 15
    assert len({case.case_id for case in cases}) == 15
    assert {case.scope for case in cases} == {"selected", "library"}
    assert any(not case.expected_evidence for case in cases)
    assert any(case.query.startswith("人工智能") for case in cases)


def test_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    line = (
        '{"case_id":"same","category":"library_retrieval","query":"q",'
        '"scope":"library","minimum_citations":0}'
    )
    path = tmp_path / "duplicate.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate"):
        load_eval_cases(path)
