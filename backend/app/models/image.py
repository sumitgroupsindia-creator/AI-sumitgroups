import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class UploadedFile(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "uploaded_files"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # uuid.ext
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)  # metadata only, never used as a path
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user = relationship("User", back_populates="uploaded_files")


class GenerationRequest(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "generation_requests"
    __table_args__ = (Index("ix_gen_requests_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # Set when the generation was started from a conversation, so chat replies and generated images
    # can be replayed as one timeline. Null for generations made outside any conversation.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    upload_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | processing | completed | partial | failed
    request_ref: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # observability request_id

    user = relationship("User", back_populates="generation_requests")
    results = relationship(
        "GenerationResult", back_populates="request", cascade="all, delete-orphan", order_by="GenerationResult.created_at"
    )


class GenerationResult(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "generation_results"
    __table_args__ = (Index("ix_gen_results_request", "request_id"),)

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_requests.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # openai | gemini
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | processing | completed | failed
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generation_results.id", ondelete="SET NULL"), nullable=True
    )
    generated_image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_images.id", ondelete="SET NULL"), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    request = relationship("GenerationRequest", back_populates="results")
    image = relationship("GeneratedImage", foreign_keys=[generated_image_id])


class GeneratedImage(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "generated_images"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="image/png")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProviderConfig(Base, UUIDPKMixin, TimestampMixin):
    """One provider slot, and the economics of using it.

    Prices are never read straight off this row — `app.services.pricing_service` owns that, so the
    reservation, the refund and the figure shown to the customer all come from one calculation.
    """

    __tablename__ = "provider_configs"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # openai | gemini
    capability: Mapped[str] = mapped_column(String(20), nullable=False)  # chat | image
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    # What the vendor bills us for one operation, in rupees. Recorded to four places because a
    # single chat turn can cost a fraction of a paisa, and rounding those to zero would make the
    # margin report claim a cost-free product.
    provider_cost_inr: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    # Credits charged to the customer, before margin. One credit is one rupee.
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Added on top, per operation. This is the profit, and it is deliberately a plain number of
    # credits rather than a percentage so an administrator can read it as rupees earned.
    margin_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
