from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_serializer


class AdminUserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUsageBreakdownRow(BaseModel):
    """One customer's spend on one slot, for one kind of operation."""

    provider: str
    operation: str
    operations: int
    credits_charged: Decimal
    # What the vendor actually billed us for this customer's work. Admin-only, always: it is our
    # supplier price, and the customer-facing /usage endpoint deliberately omits it.
    vendor_cost_inr: Decimal
    profit_inr: Decimal
    input_tokens: int
    output_tokens: int

    @field_serializer("credits_charged")
    def _credits_as_number(self, value: Decimal) -> float:
        return float(value)


class AdminUserUsageRecord(BaseModel):
    """One line of the ledger, as an administrator sees it — vendor cost included."""

    id: UUID
    provider: str
    model: str
    operation: str
    credits_consumed: Decimal
    cost_inr: Decimal
    input_tokens: int | None
    output_tokens: int | None
    status: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("credits_consumed")
    def _credits_as_number(self, value: Decimal) -> float:
        return float(value)


class AdminUserDetailResponse(BaseModel):
    """Everything about one customer's account in one payload: who they are, what they are paying
    for, what is left in their wallet, and what their usage actually cost us.

    Assembled server-side rather than left to the client to stitch together from four endpoints,
    because the interesting number — profit on this customer — is a subtraction across two of them
    and would otherwise be computed differently in every screen that showed it.
    """

    id: UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime

    # Current plan, from the live subscription. Null when they have never subscribed — which is
    # not the same as being on the free plan, and is shown differently.
    plan_code: str | None
    plan_name: str | None
    plan_price: Decimal | None
    plan_monthly_credits: int | None
    subscription_status: str | None
    current_period_end: datetime | None

    credits_balance: Decimal

    # Lifetime totals, from the ledger rather than from today's prices.
    total_operations: int
    total_credits_charged: Decimal
    total_vendor_cost_inr: Decimal
    total_profit_inr: Decimal
    total_input_tokens: int
    total_output_tokens: int

    breakdown: list[AdminUsageBreakdownRow]
    recent: list[AdminUserUsageRecord]

    @field_serializer("credits_balance", "total_credits_charged")
    def _credits_as_number(self, value: Decimal) -> float:
        return float(value)


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
    # Flat credits added on top of whatever the vendor billed. This is the profit per operation.
    margin_credits: Decimal
    # Per-million-token rates and the multiplier applied to them. Zero rates mean the slot is billed
    # flat, per operation, from the three fields above.
    input_cost_per_mtok_inr: Decimal
    output_cost_per_mtok_inr: Decimal
    markup_multiplier: Decimal
    is_metered: bool
    # What one operation charges. Exact for a flat slot; a representative turn for a metered one.
    charge_credits: Decimal
    profit_inr: Decimal
    display_name: str

    # Credits are a quantity the admin UI does arithmetic on, so this one goes out as a number. The
    # rupee fields stay Decimal-as-string, which is what they already were and what the client
    # parses them as.
    @field_serializer("charge_credits")
    def _charge_as_number(self, value: Decimal) -> float:
        return float(value)


class AdminUpdateProviderConfigRequest(BaseModel):
    is_enabled: bool | None = None
    # What we pay the vendor for one flat-priced operation, in rupees. Ignored on a metered slot,
    # where the bill comes from the token rates below.
    provider_cost_inr: Decimal | None = Field(default=None, ge=0)
    # Profit added on top of every operation, in credits. Charged per generated image, so asking
    # both slots earns it twice. Fractional: a chat turn earns half a credit.
    margin_credits: Decimal | None = Field(default=None, ge=0)
    # Rupees per million tokens, copied from the vendor's published price list. Setting either to a
    # non-zero value switches this slot to metered billing; setting both back to zero returns it to
    # the flat price.
    input_cost_per_mtok_inr: Decimal | None = Field(default=None, ge=0)
    output_cost_per_mtok_inr: Decimal | None = Field(default=None, ge=0)
    # What the customer pays per rupee of vendor cost. 1.0 sells at cost; 2.0 doubles it.
    markup_multiplier: Decimal | None = Field(default=None, ge=0)
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
    # What a representative operation costs us, and what it charges.
    cost_inr: Decimal
    margin_credits: Decimal
    charge_credits: Decimal
    profit_per_op_inr: Decimal
    is_metered: bool

    @field_serializer("charge_credits")
    def _charge_as_number(self, value: Decimal) -> float:
        return float(value)

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
    requires_paid_plan: bool
    sort_order: int

    model_config = {"from_attributes": True}


class AdminUpdateProviderBrandRequest(BaseModel):
    slot: str | None = Field(default=None, min_length=1, max_length=50)
    tier: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None
    # Free accounts cannot select a slot with this set.
    requires_paid_plan: bool | None = None


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
