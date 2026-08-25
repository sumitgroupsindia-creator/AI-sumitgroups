from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr


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


class AdminStatsResponse(BaseModel):
    total_users: int
    active_subscriptions: int
    total_conversations: int
    total_generation_requests: int
    failed_generations_last_24h: int
