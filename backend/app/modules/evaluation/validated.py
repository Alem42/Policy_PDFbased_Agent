from __future__ import annotations

import asyncio
import statistics

from app.core.ai.budget import BudgetExceeded
from app.modules.evaluation import lab_repository as lab
from app.modules.evaluation import repository, runner
from app.modules.evaluation.judge import grade
from app.modules.evaluation.metrics import aggregate, normalized


def requirement_recall(case, chunks, mapping):
    groups = case.get("requirements", [])
    if not groups:
        return None
    hits = []
    for requirement in groups:
        hits.append(
            any(
                str(chunk.get("document_id")) == mapping.get(a["source_id"])
                and chunk.get("page_start", 0) <= a["page"] <= chunk.get("page_end", 0)
                and normalized(a["quote"]) in normalized(chunk.get("text", ""))
                for a in requirement["alternatives"]
                for chunk in chunks
            )
        )
    return sum(hits) / len(hits)


def summarize(results):
    completed = [r for r in results if r.get("status") == "completed"]
    result = aggregate(results)
    judged = [r["judge"] for r in completed if r.get("judge") and not r["judge"].get("uncertain")]
    result.update(
        {
            "semantic_quality": "LLM_judge_scored; human review optional"
            if judged
            else "not_scored",
            "judge_scored": len(judged),
            "judge_errors": sum(bool(r.get("judge_error")) for r in completed),
            "mean_judge_score": statistics.mean(j["score"] for j in judged) if judged else None,
            "judge_uncertain": sum(bool(r.get("judge", {}).get("uncertain")) for r in completed),
            "post_generation_blocked": sum(
                r.get("pre_generation_allow", False) and not r["actual_allow"] for r in completed
            ),
            "full_reference_coverage_rate": statistics.mean(
                r.get("requirement_recall") == 1 for r in completed if r["expected_allow"]
            )
            if any(r["expected_allow"] for r in completed)
            else None,
        }
    )
    return result


async def run_validated(run):
    source_ids = sorted({s for c in run["cases"] for s in c["source_ids"]})
    frozen = await asyncio.to_thread(runner.snapshot, source_ids)
    # Retain the live index actually used, even when the parent is an offline experiment.
    await asyncio.to_thread(lab.artifact, run, "live_snapshot", frozen)
    semaphore = asyncio.Semaphore(1)
    lock = asyncio.Lock()
    results = dict(run["results"])
    inverse = {v: k for k, v in frozen["mapping"].items()}

    async def one(case):
        if case["id"] in results:
            return
        async with semaphore:
            if not await asyncio.to_thread(repository.heartbeat, run):
                raise RuntimeError("Run cancelled or lease lost.")
            if await asyncio.to_thread(runner.snapshot, source_ids) != frozen:
                raise RuntimeError("Live settings or corpus changed; stop this comparison.")
            try:
                result = await runner.run_case(case, run["config"], frozen)
                result.update(
                    category=case.get("category", "legacy"),
                    split=case.get("split", "legacy"),
                    requirement_recall=requirement_recall(
                        case, result.get("chunks", []), frozen["mapping"]
                    ),
                )
                # Keep UUIDs for provenance and stable source IDs for the independent judge.
                judge_result = {
                    **result,
                    "chunks": [
                        {**c, "source_id": inverse.get(str(c.get("document_id")))}
                        for c in result.get("chunks", [])
                    ],
                }
                if run["config"].get("judge_enabled", False):
                    try:
                        result["judge"] = await asyncio.to_thread(
                            grade, case, judge_result, run["config"]["judge_model"]
                        )
                    except BudgetExceeded:
                        # Keep the generated output even if no judge budget remains.
                        result["judge_skipped"] = "API budget exhausted"
                    except Exception as exc:
                        result["judge_error"] = str(exc)
                else:
                    result["judge_skipped"] = "Disabled to save tokens"
            except BudgetExceeded:
                raise
            except Exception as exc:
                result = {
                    "case_id": case["id"],
                    "question": case["question"],
                    "status": "error",
                    "error": str(exc),
                }
            if await asyncio.to_thread(runner.snapshot, source_ids) != frozen:
                raise RuntimeError("Live settings or corpus changed during a case.")
            async with lock:
                results[case["id"]] = result
                metrics = {
                    **summarize(list(results.values())),
                    "stage": "answers_and_judge",
                    "case_count": len(run["cases"]),
                }
                await asyncio.to_thread(repository.record, run, result, metrics)

    await asyncio.gather(*(one(c) for c in run["cases"]))
    by_split = {
        split: summarize([r for r in results.values() if r.get("split") == split])
        for split in ("calibration", "validation", "diagnostic")
    }
    await asyncio.to_thread(lab.artifact, run, "by_split", by_split)


BAD_ANSWERS = [
    "The four functions are Govern, Publish, Measure and Manage. [1]",
    "Confabulation is confidently stated information that is always factually correct. [1]",
    "The five principles are only fairness and transparency; no others apply. [1]",
    "不满十四周岁的未成年人可以仅凭本人的同意处理个人信息，不需要监护人同意。[1]",
    "数据分类分级仅根据经济价值，不考虑泄露等造成的危害。[1]",
    "The five privacy functions are Govern, Identify, Protect, Detect and Recover. [1]",
    "The 2030 offshore wind target is 40 megawatts, including 1 megawatt of floating wind. [1]",
    "The 2030 target is 83% below 2005 emissions. [1]",
    "This agreement helps only wealthy homeowners and excludes people at risk of homelessness. [1]",
    "CSF 2.0 has exactly four functions: Govern, Identify, Protect and Recover. [1]",
    "The incident-response functions are Identify, Prevent and Manage. [1]",
    "The biological risk pillars are only Understand and Prevent; "
    "Detect and Respond are excluded. [1]",
]


async def judge_controls(run):
    from app.modules.evaluation import experiments
    from app.modules.evidence_validation.config import EvidenceValidationConfig
    from app.modules.evidence_validation.service import validate_answer

    pages = await asyncio.to_thread(experiments.sources)
    base = [c for c in run["cases"] if c["id"].startswith("F") and c["id"].endswith("A")]
    reports = []
    semaphore = asyncio.Semaphore(3)

    async def one(index, case, mutated):
        async with semaphore:
            anchor = case["requirements"][0]["alternatives"][0]
            page = next(p for p in pages[anchor["source_id"]] if p["page"] == anchor["page"])
            chunk = {
                "chunk_id": "control",
                "document_id": anchor["source_id"],
                "source_id": anchor["source_id"],
                "page_start": anchor["page"],
                "page_end": anchor["page"],
                "text": page["text"],
            }
            answer = (
                BAD_ANSWERS[index] if mutated else case["requirements"][0]["reference"] + " [1]"
            )
            report = await asyncio.to_thread(
                validate_answer,
                case["question"],
                answer,
                [chunk],
                EvidenceValidationConfig(enabled=True),
            )
            result = {
                "actual_allow": True,
                "answer": answer,
                "chunks": [chunk],
                "citations": [
                    {
                        "document_id": anchor["source_id"],
                        "page": anchor["page"],
                        "quote": page["text"][:500],
                    }
                ],
            }
            judged = (
                await asyncio.to_thread(grade, case, result, run["config"]["judge_model"])
                if run["config"].get("judge_enabled", False)
                else None
            )
            expected = not mutated
            out = {
                "case_id": case["id"] + ("-mutation" if mutated else "-correct"),
                "expected_supported": expected,
                "guard_allowed": report["allowed"],
                "guard_correct": report["allowed"] == expected,
                "guard_report": report,
                "answer": answer,
                "judge": judged,
                "judge_correct": None
                if judged is None
                else (
                    min(judged["groundedness"], judged["completeness"], judged["citation_support"])
                    >= 3
                )
                == expected,
            }
            reports.append(out)
            await asyncio.to_thread(lab.artifact, run, out["case_id"], out)
            await asyncio.to_thread(
                lab.progress,
                run,
                {"stage": "judge_controls", "completed": len(reports), "controls": len(base) * 2},
            )

    await asyncio.gather(*(one(i, c, m) for i, c in enumerate(base) for m in (False, True)))
    await asyncio.to_thread(
        lab.artifact,
        run,
        "controls_summary",
        {
            "controls": len(reports),
            "guard_correct": sum(r["guard_correct"] for r in reports),
            "judge_correct": sum(r["judge_correct"] is True for r in reports),
            "judge_scored": sum(r["judge"] is not None for r in reports),
            "failures": [
                r for r in reports if not r["guard_correct"] or r["judge_correct"] is False
            ],
        },
    )
