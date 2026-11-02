"""Run or inspect an explicitly requested real-data experiment, without logging keys."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core.database import get_connection
from app.modules.evaluation import experiments, lab_repository as lab, repository, runner
from app.modules.evaluation.repository import encode
from app.modules.local_models.runtime import local_model_runtime


def export(identifier):
    run = repository.get(identifier)
    run["artifacts"] = lab.artifacts(identifier)
    out = Path("eval-results/experiment-v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{identifier}.json").write_text(encode(run), encoding="utf8")
    print(
        json.dumps(
            {
                "id": identifier,
                "status": run["status"],
                "metrics": run["metrics"],
                "error": run["error"],
            },
            default=str,
            ensure_ascii=False,
        ),
        flush=True,
    )


async def execute(kind, parent=None):
    from app.modules.evaluation.service import settings
    from app.modules.evaluation.sampling import balanced

    current = settings()
    if kind == "audit" and not current.allow_full_source_audit:
        raise ValueError("Full-document audit disabled by the API budget settings.")
    cases = experiments.extended_cases()
    if kind not in ("chunk_sweep", "parameter_sweep"):
        cases = balanced(cases, current.max_cases)
    identifier, token = str(uuid4()), str(uuid4())
    frozen = runner.snapshot(sorted({s for c in cases for s in c["source_ids"]}))
    config = {
        **current.model_dump(mode="json"),
        "kind": kind,
        "suite": "extended",
        "case_ids": [],
        "parent_run_id": parent,
    }
    with get_connection() as conn:
        actor = conn.execute(
            "SELECT id FROM app_users WHERE role='admin' ORDER BY created_at LIMIT 1"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO evaluation_runs(id,status,requested_by,config,snapshot,cases,lease_token,lease_expires_at,started_at) "
            "VALUES (%s,'running',%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,now()+interval '90 seconds',now())",
            (identifier, actor, encode(config), encode(frozen), encode(cases), token),
        )
    run = repository.get(identifier)
    print(json.dumps({"id": identifier, "kind": kind, "cases": len(cases)}), flush=True)

    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            if not await asyncio.to_thread(repository.heartbeat, run):
                return

    pulse = asyncio.create_task(heartbeat())
    from app.core.ai import budget

    allowance = budget.LLMBudget()
    try:
        with budget.scope(config) as allowance:
            if kind == "chunk_sweep":
                await asyncio.to_thread(experiments.chunk_sweep, run)
            elif kind == "parameter_sweep":
                if not parent:
                    raise ValueError("A completed chunk-sweep parent is required.")
                await asyncio.to_thread(
                    experiments.parameter_sweep, run, {"id": parent, **lab.artifacts(parent)}
                )
            elif kind in ("validated", "baseline"):
                from app.modules.evaluation.validated import run_validated

                await run_validated(run)
            elif kind == "judge_controls":
                from app.modules.evaluation.validated import judge_controls

                await judge_controls(run)
            elif kind == "audit":
                from app.modules.evaluation.judge import audit_dataset

                await audit_dataset(run)
        lab.artifact(run, "api_budget", allowance.snapshot())
        repository.finish(run)
    except budget.BudgetExceeded as exc:
        if repository.heartbeat(run):
            lab.artifact(run, "api_budget", allowance.snapshot())
        repository.finish(run, "cancelled", str(exc))
    except Exception as exc:
        repository.finish(run, "failed", str(exc))
        raise
    finally:
        pulse.cancel()
        await asyncio.gather(pulse, return_exceptions=True)
        await asyncio.to_thread(local_model_runtime.unload)
        export(identifier)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=[
            "chunk_sweep",
            "parameter_sweep",
            "validated",
            "baseline",
            "judge_controls",
            "audit",
            "status",
        ],
    )
    parser.add_argument("--parent")
    parser.add_argument("--id")
    args = parser.parse_args()
    if args.kind == "status":
        export(args.id)
    else:
        asyncio.run(execute(args.kind, args.parent))
