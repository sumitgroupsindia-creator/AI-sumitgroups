from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    provider: str = Field(default="openai", pattern="^(openai|gemini)$")
    model: str | None = None


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    provider: str | None
    model: str | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    model: str
    provider: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
