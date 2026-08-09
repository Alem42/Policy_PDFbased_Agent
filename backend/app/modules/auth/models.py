from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.auth.schemas import UserRole


class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_users"

    uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Text, nullable=False, server_default=text("'user'"))


class AdminInviteModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "admin_invites"

    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    code_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_users.id"), nullable=True
    )
    consumed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_users.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
