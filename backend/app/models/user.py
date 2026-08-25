import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # OAuth-extensibility: null for password-based accounts.
    auth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    credits = relationship("Credit", back_populates="user", uselist=False, cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    uploaded_files = relationship("UploadedFile", back_populates="user", cascade="all, delete-orphan")
    generation_requests = relationship("GenerationRequest", back_populates="user", cascade="all, delete-orphan")


class PasswordReset(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
