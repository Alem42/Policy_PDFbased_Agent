from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.core.database import get_connection

TOKEN_TTL_SECONDS = 60 * 60 * 24
PASSWORD_ALGORITHM = "pbkdf2_sha256"


def _secret_key() -> bytes:
    return get_settings().app_secret.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt, expected_digest = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != PASSWORD_ALGORITHM:
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def _next_uid() -> str:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT uid
            FROM app_users
            ORDER BY uid DESC
            LIMIT 1
            """
        ).fetchone()
    next_value = int(row["uid"]) + 1 if row else 0
    return f"{next_value:05d}"


def _public_user(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "uid": row["uid"],
        "username": row["username"],
        "role": row["role"],
        "created_at": row["created_at"].isoformat(),
    }


def create_user(username: str, password: str, role: str | None = None) -> dict:
    clean_username = username.strip()
    if len(clean_username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if not password:
        raise ValueError("Password is required.")
    clean_role = role or "user"
    if clean_role not in {"admin", "user"}:
        raise ValueError("Role must be admin or user.")

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO app_users (id, uid, username, password_hash, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, uid, username, role, created_at
            """,
            (
                str(uuid4()),
                _next_uid(),
                clean_username,
                hash_password(password),
                clean_role,
            ),
        ).fetchone()
        connection.commit()
    return _public_user(row)


def authenticate_user(username: str, password: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, uid, username, password_hash, role, created_at
            FROM app_users
            WHERE username = %s
            """,
            (username.strip(),),
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return _public_user(row)


def create_access_token(user: dict) -> str:
    payload = {
        "sub": user["uid"],
        "username": user["username"],
        "role": user["role"],
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret_key(), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_part}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid token.") from exc
    expected_signature = hmac.new(
        _secret_key(),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected_signature), signature_part):
        raise ValueError("Invalid token signature.")
    payload = json.loads(_b64url_decode(payload_part))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired.")
    return payload


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, uid, username, role, created_at
            FROM app_users
            WHERE uid = %s
            """,
            (payload["sub"],),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )
    return _public_user(row)


def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return get_current_user(authorization)


def require_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required.",
        )
    return user
