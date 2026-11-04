from __future__ import annotations

import asyncio
import logging

from app.core.ai import budget
from app.core.ai.chat_models import resolve_generation_target
from app.core.config import get_settings
from app.core.database import get_connection
from app.core.settings_store import SingleRowSettings
from app.modules.evaluation import corpus, repository, runner
from app.modules.evaluation.config import EvaluationConfig
from app.modules.evaluation.metrics import aggregate
from app.modules.settings.service import get_provider_api_key
from app.modules.usage.context import usage_scope

logger = logging.getLogger(__name__)
settings_store = SingleRowSettings("evaluation_settings")


def settings():
    return EvaluationConfig(**settings_store.load())


def save_settings(payload):
    settings_store.save(payload.model_dump_json())
    return payload


def start_run(payload, actor):
    from app.modules.evaluation.experiments import extended_cases

    all_cases = extended_cases() if payload.suite == "extended" else corpus.cases()
    known = {c["id"] for c in all_cases}
    if set(payload.case_ids) - known:
        raise ValueError("Unknown evaluation case ID.")
    selected = [c for c in all_cases if not payload.case_ids or c["id"] in payload.case_ids]
    if not selected:
        raise ValueError("Select at least one case.")
    if payload.kind == "audit" and not payload.allow_full_source_audit:
        raise ValueError(
            "Full-document audit is disabled to save tokens; explicitly enable it first."
        )
    if payload.reuse_run_id:
        previous = repository.get(str(payload.reuse_run_id))
        # Continuations always refer to the original run so repeated small
        # batches also skip work completed by their earlier sibling batches.
        while previous["config"].get("reuse_run_id"):
            previous = repository.get(str(previous["config"]["reuse_run_id"]))
        payload = payload.model_copy(update={"reuse_run_id": previous["id"]})
        if previous["status"] in ("queued", "running"):
            raise ValueError("Cancel the previous run before starting its unfinished cases.")
        if previous["snapshot"] != runner.snapshot(
            [s for c in previous["cases"] for s in c["source_ids"]]
        ):
            raise ValueError(
                "Previous source index/settings differ; cached outputs cannot be mixed."
            )
        done = repository.completed_case_ids(str(previous["id"]))
        previous_ids = {c["id"] for c in previous["cases"]}
        selected = [c for c in selected if c["id"] in previous_ids and c["id"] not in done]
        if not selected:
            raise ValueError("There are no unfinished cases in the selected run.")
    if payload.kind not in ("chunk_sweep", "parameter_sweep", "retrieval_lab"):
        from app.modules.evaluation.sampling import balanced

        selected = balanced(selected, payload.max_cases)
    provider, _, _ = resolve_generation_target(payload.model)
    if not get_provider_api_key(provider):
        raise ValueError(f"Configure a generation API key for {provider} before running.")
    frozen = runner.snapshot([s for c in selected for s in c["source_ids"]])
    return repository.create(payload.model_dump(), frozen, selected, actor)


def latest_chunk_run():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM evaluation_runs WHERE status='completed' "
            "AND config->>'kind' IN ('chunk_sweep','retrieval_lab') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise ValueError("Complete a chunk sweep first.")
    return str(row["id"])


class EvaluationWorker:
    """Leased persistent runs; restart resumes completed cases, not partial answers."""

    def __init__(self):
        self._task = None

    async def start(self):
        if get_settings().database_enabled and self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _heartbeat(self, run):
        while True:
            await asyncio.sleep(20)
            if not await asyncio.to_thread(repository.heartbeat, run):
                return

    async def _execute(self, run):
        requester = run.get("requested_by")
        with usage_scope(area="evaluation", operation=run.get("config", {}).get("kind", "baseline"),
                         user_id=str(requester) if requester else None):
            await self._execute_run(run)

    async def _execute_run(self, run):
        pulse = asyncio.create_task(self._heartbeat(run))
        try:
            config = run.get("config", {})
            kind = config.get("kind", "baseline")
            if kind != "baseline" or config.get("suite") in ("legacy", "extended"):
                with budget.scope(config) as allowance:
                    try:
                        await self._experiment(run, kind)
                    finally:
                        if await asyncio.to_thread(repository.heartbeat, run):
                            from app.modules.evaluation import lab_repository as lab

                            await asyncio.to_thread(
                                lab.artifact, run, "api_budget", allowance.snapshot()
                            )
                await asyncio.to_thread(repository.finish, run)
                return
            source_ids = [s for c in run["cases"] for s in c["source_ids"]]
            for case in run["cases"]:
                if case["id"] in run["results"]:
                    continue
                if not await asyncio.to_thread(repository.heartbeat, run):
                    return
                current = await asyncio.to_thread(runner.snapshot, source_ids)
                if current != run["snapshot"]:
                    raise ValueError(
                        "Retrieval settings or document index changed; create a new run."
                    )
                try:
                    result = await runner.run_case(case, run["config"], run["snapshot"])
                except Exception as exc:
                    result = {
                        "case_id": case["id"],
                        "question": case["question"],
                        "status": "error",
                        "error": str(exc),
                    }
                if await asyncio.to_thread(runner.snapshot, source_ids) != run["snapshot"]:
                    raise ValueError(
                        "Index/settings changed during a case; output was not published."
                    )
                run["results"][case["id"]] = result
                await asyncio.to_thread(
                    repository.record, run, result, aggregate(list(run["results"].values()))
                )
            await asyncio.to_thread(repository.finish, run)
        except budget.BudgetExceeded as exc:
            await asyncio.to_thread(repository.finish, run, "cancelled", str(exc))
        except asyncio.CancelledError:
            await asyncio.to_thread(repository.release, run)
            raise
        except Exception as exc:
            logger.exception("Evaluation run failed: %s", run["id"])
            await asyncio.to_thread(repository.finish, run, "failed", str(exc))
        finally:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)

    async def _experiment(self, run, kind):
        from app.modules.evaluation import experiments
        from app.modules.evaluation import lab_repository as lab

        if kind in ("chunk_sweep", "retrieval_lab"):
            await asyncio.to_thread(experiments.chunk_sweep, run)
            if kind == "retrieval_lab":
                await asyncio.to_thread(
                    experiments.parameter_sweep,
                    run,
                    {"id": str(run["id"]), **lab.artifacts(run["id"])},
                )
        elif kind == "parameter_sweep":
            parent = run["config"].get("parent_run_id")
            if not parent:
                parent = await asyncio.to_thread(latest_chunk_run)
            await asyncio.to_thread(
                experiments.parameter_sweep, run, {"id": parent, **lab.artifacts(parent)}
            )
        elif kind in ("validated", "baseline"):
            from app.modules.evaluation.validated import run_validated

            await run_validated(run)
        elif kind == "audit":
            from app.modules.evaluation.judge import audit_dataset

            await audit_dataset(run)
        elif kind == "judge_controls":
            from app.modules.evaluation.validated import judge_controls

            await judge_controls(run)

    async def _loop(self):
        while True:
            try:
                run = await asyncio.to_thread(repository.claim)
                if run:
                    await self._execute(run)
                else:
                    await asyncio.sleep(3)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Evaluation queue unavailable; apply migration 029 if missing.")
                await asyncio.sleep(10)


evaluation_worker = EvaluationWorker()
