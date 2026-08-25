from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PlanResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    billing_interval: str
    monthly_chat_credits: int
    monthly_image_credits: int
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
    chat_balance: int
    image_balance: int


class UsageRecordResponse(BaseModel):
    """`model` is omitted deliberately — users see neutral model slots, not vendor model ids."""

    id: UUID
    provider: str
    operation: str
    credits_consumed: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
