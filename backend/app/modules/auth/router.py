from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthRequest, AuthResponse, UserResponse
from app.modules.auth.service import (
    authenticate_user,
    create_access_token,
    create_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: AuthRequest) -> dict:
    try:
        user = create_user(payload.username, payload.password, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Username is already taken.") from exc
    return {"token": create_access_token(user), "user": user}


@router.post("/login", response_model=AuthResponse)
async def login(payload: AuthRequest) -> dict:
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"token": create_access_token(user), "user": user}


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> dict:
    return user
