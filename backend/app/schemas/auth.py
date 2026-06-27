from enum import StrEnum

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    role: UserRole | None = None


class UserResponse(BaseModel):
    id: str
    uid: str
    username: str
    role: UserRole
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
