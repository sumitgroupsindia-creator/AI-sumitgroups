from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_serializer


class PlanResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    billing_interval: str
    monthly_credits: int
    max_upload_mb: int
    priority_queue: bool

    model_config = {"from_attributes": True}


class SubscriptionResponse(BaseModel):
    id: UUID
    status: str
    provider: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    plan: PlanResponse

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    plan_code: str


class CheckoutResponse(BaseModel):
    provider: str
    order_id: str
    amount: int
    currency: str
    key_id: str
    subscription_id: UUID


class CreditsResponse(BaseModel):
    """One wallet, in credits. One credit is one rupee.

    Sent as a JSON number, not the string Pydantic gives a Decimal by default. Clients do
    arithmetic and comparisons on this — a quiet switch to "9.9800" turns every one of those into
    string handling, and the balance would start sorting and comparing lexically.
    """

    balance: Decimal

    @field_serializer("balance")
    def _as_number(self, value: Decimal) -> float:
        return float(value)


class UsageRecordResponse(BaseModel):
    """One line of the customer's own usage.

    `model` is omitted deliberately — users see neutral model slots, not vendor model ids — and so
    is `cost_inr`, which is our supplier bill and would hand every customer the exact margin. The
    token counts are the customer's own consumption, and they are the only thing that explains why
    one message cost more than another, so they stay.
    """

    id: UUID
    provider: str
    operation: str
    credits_consumed: Decimal
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("credits_consumed")
    def _as_number(self, value: Decimal) -> float:
        return float(value)
