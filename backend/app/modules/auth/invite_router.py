from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg.errors import UndefinedColumn, UndefinedTable

from app.modules.auth.dependencies import require_admin
from app.modules.auth.invites import create_invite, list_invites, revoke_invite
from app.modules.auth.schemas import (
    AdminInviteCreatedResponse,
    AdminInviteCreateRequest,
    AdminInviteResponse,
)

router = APIRouter(prefix="/admin/invites", tags=["admin-invites"])
AdminUser = Annotated[dict, Depends(require_admin)]
SCHEMA_ERRORS = (UndefinedTable, UndefinedColumn)
MIGRATION_MESSAGE = (
    "Administrator invitation schema is out of date. Apply migration "
    "025_add_admin_invites.sql to the database used by this backend."
)


@router.get("", response_model=list[AdminInviteResponse])
async def admin_invites(_: AdminUser) -> list[dict]:
    try:
        return list_invites()
    except SCHEMA_ERRORS as exc:
        raise HTTPException(status_code=503, detail=MIGRATION_MESSAGE) from exc


@router.post(
    "",
    response_model=AdminInviteCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_admin_invite(payload: AdminInviteCreateRequest, admin: AdminUser) -> dict:
    try:
        return create_invite(
            created_by_user_id=admin["id"],
            expires_in_days=payload.expires_in_days,
        )
    except SCHEMA_ERRORS as exc:
        raise HTTPException(status_code=503, detail=MIGRATION_MESSAGE) from exc


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_invite(invite_id: UUID, _: AdminUser) -> Response:
    try:
        revoke_invite(str(invite_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SCHEMA_ERRORS as exc:
        raise HTTPException(status_code=503, detail=MIGRATION_MESSAGE) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
