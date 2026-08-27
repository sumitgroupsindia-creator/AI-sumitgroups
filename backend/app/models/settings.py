import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class AppSetting(Base, UUIDPKMixin, TimestampMixin):
    """One runtime-configurable value, overriding the matching `.env` entry when present.

    Only keys listed in `app.services.settings_service.CATALOG` are accepted, so a write cannot
    invent configuration the application does not understand. Values whose spec is a secret are
    stored sealed — see `app.core.crypto`.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(default=False, nullable=False)


class AppSettingAudit(Base, UUIDPKMixin, TimestampMixin):
    """Who changed which setting, and when.

    Secrets are recorded masked, never in the clear: the point of the trail is to show that a key
    was rotated and by whom, not to become a second place the key can be read from.
    """

    __tablename__ = "app_setting_audits"

    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    old_preview: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    new_preview: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class ProviderBrand(Base, UUIDPKMixin, TimestampMixin):
    """The customer-facing identity of a provider slot — "Model 1 · Standard".

    Real provider names (OpenAI, Gemini) are never shown to end users; the product owns the naming
    so a provider can be swapped behind a slot without customers noticing. Branding is keyed by
    provider rather than by provider_config because it applies to a provider as a whole, across both
    its chat and image rows.
    """

    __tablename__ = "provider_brands"

    provider: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    slot: Mapped[str] = mapped_column(String(50), nullable=False)  # "Model 1"
    tier: Mapped[str] = mapped_column(String(50), nullable=False)  # "Standard"
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Free accounts cannot select this slot, and therefore cannot ask both slots at once. Kept on
    # the brand so an administrator can move which slot is premium without a deploy, and so the
    # billing path never has to name a vendor.
    requires_paid_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
