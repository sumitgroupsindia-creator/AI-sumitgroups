from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUpdateUserRequest(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class AdminUpdatePlanRequest(BaseModel):
    name: str | None = None
    price: Decimal | None = None
    monthly_chat_credits: int | None = None
    monthly_image_credits: int | None = None
    max_upload_mb: int | None = None
    is_active: bool | None = None


class AdminProviderConfigResponse(BaseModel):
    id: UUID
    provider: str
    capability: str
    model: str
    is_enabled: bool
    credit_cost: int
    display_name: str

    model_config = {"from_attributes": True}


class AdminUpdateProviderConfigRequest(BaseModel):
    is_enabled: bool | None = None
    credit_cost: int | None = None
    model: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class AdminProviderBrandResponse(BaseModel):
    """How a provider slot is presented to customers, who never see the provider's real name."""

    id: UUID
    provider: str
    slot: str
    tier: str
    description: str
    sort_order: int

    model_config = {"from_attributes": True}


class AdminUpdateProviderBrandRequest(BaseModel):
    slot: str | None = Field(default=None, min_length=1, max_length=50)
    tier: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None


class AdminSettingResponse(BaseModel):
    key: str
    label: str
    group: str
    kind: str
    help: str
    options: list[str]
    value: str  # always empty for secrets — they are never returned in the clear
    masked: str
    is_secret: bool
    is_set: bool
    source: str  # "database" once overridden, otherwise "environment"
    unreadable: bool  # sealed with a key this deployment no longer holds


class AdminUpdateSettingsRequest(BaseModel):
    # Submitting a secret as "" leaves it untouched; the form cannot show the current value, so a
    # blank field is what an untouched form always looks like.
    values: dict[str, str]


class AdminSettingAuditResponse(BaseModel):
    id: UUID
    key: str
    actor_email: str
    old_preview: str
    new_preview: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminStatsResponse(BaseModel):
    total_users: int
    active_subscriptions: int
    total_conversations: int
    total_generation_requests: int
    failed_generations_last_24h: int
