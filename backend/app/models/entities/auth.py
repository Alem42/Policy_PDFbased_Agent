from sqlalchemy import Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.schemas.auth import UserRole


class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_users"

    uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Text, nullable=False, server_default=text("'user'"))
