from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.modules.auth.repository import admin_invite_repository, user_repository

DEFAULT_INVITE_DAYS = 7


def hash_invite_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _status(row: dict) -> str:
    if row.get("consumed_at"):
        return "used"
    if row.get("revoked_at"):
        return "revoked"
    if row["expires_at"] <= datetime.now(UTC):
        return "expired"
    return "active"


def public_invite(row: dict) -> dict:
    result = {**row, "id": str(row["id"]), "status": _status(row)}
    result.pop("created_by_user_id", None)
    return result


def create_invite(*, created_by_user_id: str | None, expires_in_days: int) -> dict:
    code = secrets.token_urlsafe(24)
    row = admin_invite_repository.create(
        code_hash=hash_invite_code(code),
        code_prefix=code[:8],
        created_by_user_id=created_by_user_id,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
        replace_bootstrap=created_by_user_id is None,
    )
    return {**public_invite(row), "invite_code": code}


def create_bootstrap_invite() -> dict:
    if user_repository.admin_exists():
        raise ValueError("Bootstrap is disabled because an administrator already exists.")
    return create_invite(created_by_user_id=None, expires_in_days=DEFAULT_INVITE_DAYS)


def list_invites() -> list[dict]:
    return [public_invite(row) for row in admin_invite_repository.list_all()]


def revoke_invite(invite_id: str) -> None:
    if not admin_invite_repository.revoke(invite_id):
        raise ValueError("Invitation was not found or is no longer active.")
