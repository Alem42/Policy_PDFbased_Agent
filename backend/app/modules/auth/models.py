from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.auth.schemas import UserRole


class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_users"

    uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Text, nullable=False, server_default=text("'user'"))
