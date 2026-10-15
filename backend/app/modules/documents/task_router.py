import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.modules.auth.dependencies import require_admin
from app.modules.documents.processing_queue import document_processing_queue
from app.modules.documents.repositories.tasks import ActiveDocumentTask, document_task_repository

router = APIRouter(prefix="/admin/document-tasks", tags=["admin"])
AdminUser = Annotated[dict, Depends(require_admin)]


@router.get("")
async def list_tasks(_: AdminUser, limit: int = Query(50, ge=1, le=200)) -> dict:
    result = await asyncio.to_thread(document_task_repository.list, limit)
    result["items"] = [
        {key: value for key, value in row.items() if key != "lease_token"}
        for row in result["items"]
    ]
    result["workers_per_process"] = get_settings().document_task_workers
    return result


@router.post("/{task_id}/retry", status_code=202)
async def retry_task(task_id: UUID, _: AdminUser) -> dict:
    try:
        task = await asyncio.to_thread(document_task_repository.retry, str(task_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActiveDocumentTask as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    document_processing_queue.notify()
    return {key: value for key, value in task.items() if key != "lease_token"}
