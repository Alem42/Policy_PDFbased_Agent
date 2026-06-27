from sqlalchemy import Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.auth.schemas import UserRole


class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_users"

    uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Text, nullable=False, server_default=text("'user'"))
