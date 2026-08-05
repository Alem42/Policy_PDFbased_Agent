from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.modules.auth.repository import user_repository
from app.modules.auth.service import decode_access_token, public_user


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    row = user_repository.find_by_uid(payload["sub"])
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
        )
    return public_user(row)


def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        # A stale/invalid token on an endpoint that allows anonymous access
        # degrades to anonymous instead of failing the whole request.
        return None


def require_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required.",
        )
    return user
