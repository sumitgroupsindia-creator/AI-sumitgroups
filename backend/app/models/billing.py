import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Plan(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # free | pro | business
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False, default="month")  # month|year
    monthly_chat_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_image_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_upload_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    priority_queue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | active | past_due | cancelled | expired
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="razorpay")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")


class Credit(Base, UUIDPKMixin, TimestampMixin):
    """One row per user; balance is mutated transactionally (SELECT ... FOR UPDATE)."""

    __tablename__ = "credits"
    __table_args__ = (UniqueConstraint("user_id", name="uq_credits_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    chat_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="credits")


class UsageRecord(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "usage_records"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)  # chat | image_generate | image_edit
    credits_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class IdempotencyKey(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
