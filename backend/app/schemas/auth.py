from typing import Literal

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    role: Literal["admin", "user"] | None = None


class UserResponse(BaseModel):
    id: str
    uid: str
    username: str
    role: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
