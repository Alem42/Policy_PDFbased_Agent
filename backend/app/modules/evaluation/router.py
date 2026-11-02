import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import require_admin
from app.modules.evaluation import corpus, lab_repository, repository, service
from app.modules.evaluation.config import EvaluationConfig, Review
from app.modules.evaluation.experiments import extended_cases
from app.modules.evidence_validation import service as evidence_validation
from app.modules.local_models.runtime import local_model_runtime

router = APIRouter(prefix="/admin/evaluation", tags=["admin"])
Admin = Annotated[dict, Depends(require_admin)]


@router.get("")
async def overview(_: Admin):
    def load():
        return {
            "settings": service.settings(),
            "cases": extended_cases(),
            "legacy_cases": corpus.cases(),
            "corpus": corpus.manifest(),
            "mapping": corpus.mapping(),
            "runs": repository.recent(),
            "runtime": local_model_runtime.status(),
            "validation_settings": evidence_validation.config(),
        }

    return await asyncio.to_thread(load)


@router.put("")
async def update(payload: EvaluationConfig, _: Admin):
    return await asyncio.to_thread(service.save_settings, payload)


@router.post("/corpus")
async def install(admin: Admin):
    try:
        return await corpus.install(str(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs", status_code=202)
async def start(payload: EvaluationConfig, admin: Admin):
    try:
        identifier = await asyncio.to_thread(service.start_run, payload, str(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": identifier, "status": "queued"}


@router.get("/runs/{identifier}")
async def detail(identifier: UUID, _: Admin):
    try:
        result = await asyncio.to_thread(repository.get, str(identifier))
        result["artifacts"] = await asyncio.to_thread(lab_repository.artifacts, str(identifier))
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/runs/{identifier}/cancel")
async def cancel(identifier: UUID, _: Admin):
    try:
        await asyncio.to_thread(repository.cancel, str(identifier))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "cancelled"}


@router.put("/runs/{identifier}/reviews/{case_id}")
async def review(identifier: UUID, case_id: str, payload: Review, admin: Admin):
    try:
        await asyncio.to_thread(
            repository.review, str(identifier), case_id, payload, str(admin["id"])
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"saved": True}


@router.post("/unload")
async def unload(_: Admin):
    await asyncio.to_thread(local_model_runtime.unload)
    return local_model_runtime.status()


@router.put("/validation")
async def validation_settings(payload: dict, _: Admin):
    try:
        return await asyncio.to_thread(evidence_validation.save_config, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{identifier}/apply", status_code=202)
async def apply_configuration(identifier: UUID, _: Admin):
    from app.modules.evaluation.publish import publish

    try:
        return await publish(str(identifier))
    except (LookupError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
