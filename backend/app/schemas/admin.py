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
    monthly_credits: int | None = Field(default=None, ge=0)
    max_upload_mb: int | None = None
    is_active: bool | None = None


class AdminProviderConfigResponse(BaseModel):
    """A slot's wiring and its economics. One credit is one rupee, so `charge_credits` doubles as
    the revenue in rupees and `profit_inr` is simply the charge less what the vendor bills us."""

    id: UUID
    provider: str
    capability: str
    model: str
    is_enabled: bool
    provider_cost_inr: Decimal
    credit_cost: int
    margin_credits: int
    charge_credits: int
    profit_inr: Decimal
    display_name: str


class AdminUpdateProviderConfigRequest(BaseModel):
    is_enabled: bool | None = None
    # What we pay the vendor for one operation, in rupees.
    provider_cost_inr: Decimal | None = Field(default=None, ge=0)
    # What the customer pays before margin, in credits.
    credit_cost: int | None = Field(default=None, ge=0)
    # Profit added on top of every operation, in credits. Charged per generated image, so asking
    # both slots earns it twice.
    margin_credits: int | None = Field(default=None, ge=0)
    model: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class AdminPricingRow(BaseModel):
    """One slot's current price alongside what it actually earned over the reporting window."""

    provider: str
    capability: str
    model: str
    display_name: str
    is_enabled: bool

    # Current price, per operation.
    cost_inr: Decimal
    base_credits: int
    margin_credits: int
    charge_credits: int
    profit_per_op_inr: Decimal

    # What happened over the window, from the ledger rather than from today's prices.
    operations: int
    revenue_inr: Decimal
    spend_inr: Decimal
    profit_inr: Decimal


class AdminPricingResponse(BaseModel):
    days: int
    rows: list[AdminPricingRow]
    total_operations: int
    total_revenue_inr: Decimal
    total_spend_inr: Decimal
    total_profit_inr: Decimal


class AdminPromptTemplateResponse(BaseModel):
    """One master prompt. `kind` decides when it applies — see `app.models.prompt.PromptTemplate`."""

    id: UUID
    key: str
    scope: str  # chat | image
    kind: str  # base | task | tool
    name: str
    description: str
    content: str
    is_enabled: bool
    sort_order: int

    model_config = {"from_attributes": True}


class AdminUpdatePromptTemplateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # Read by the router when deciding whether a task fits, so editing it changes behaviour, not
    # just the admin screen's wording.
    description: str | None = Field(default=None, max_length=500)
    content: str | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None


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
