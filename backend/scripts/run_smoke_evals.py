"""Run the version-controlled policy-search smoke evaluation dataset."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.modules.chat.capabilities.policy_search import policy_search_capability
from app.modules.evaluation.dataset import load_eval_cases
from app.modules.evaluation.reporting import write_experiment_reports
from app.modules.evaluation.runner import run_experiment

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = BACKEND_ROOT / "evals/smoke_policy_search.jsonl"
DEFAULT_OUTPUT = BACKEND_ROOT / "eval-results"


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    cases = load_eval_cases(args.dataset)
    experiment = await run_experiment(
        cases,
        policy_search_capability,
        dataset_path=args.dataset,
        max_concurrency=args.max_concurrency,
    )
    json_path, markdown_path = write_experiment_reports(experiment, args.output)
    print(
        f"Evaluation: {experiment.passed_count}/{experiment.case_count} "
        f"({experiment.pass_rate:.1%}), mean latency {experiment.mean_latency_ms:.3f} ms"
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return int(args.fail_on_regression and experiment.pass_rate < 1.0)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
