import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class LoginRequest(BaseModel):
    # Kept as "username" for backwards API compatibility; an email is accepted too.
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    password_confirmation: str = Field(min_length=8, max_length=256)
    verification_code: str = Field(pattern=r"^\d{6}$")
    role: UserRole | None = None
    secret: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", clean):
            raise ValueError("Enter a valid email address.")
        return clean

    @model_validator(mode="after")
    def passwords_match(self) -> "RegistrationRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        return self


class VerificationCodeRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", clean):
            raise ValueError("Enter a valid email address.")
        return clean


class VerificationCodeResponse(BaseModel):
    message: str
    expires_in: int
    retry_after: int
    development_code: str | None = None


class UserResponse(BaseModel):
    id: str
    uid: str
    username: str
    email: str | None = None
    email_verified: bool = False
    role: UserRole
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
