from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.providers.registry import AVAILABLE_PROVIDERS


class ChatStreamRequest(BaseModel):
    """`providers` are opaque slot keys ("Model 1"/"Model 2" in the UI). The concrete vendor model is
    resolved server-side from provider_configs — clients cannot choose or even see it.

    Passing two runs the same turn through both and streams the answers together, each event tagged
    with the slot it came from.
    """

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=8000)
    providers: list[str] = Field(default_factory=lambda: ["openai"], min_length=1, max_length=2)
    upload_file_id: UUID | None = None

    @field_validator("providers")
    @classmethod
    def _known_and_unique(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for name in value:
            if name not in AVAILABLE_PROVIDERS:
                raise ValueError(f"Unknown provider: {name}")
            if name not in deduped:
                deduped.append(name)
        return deduped


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    provider: str | None
    error: str | None
    upload_file_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    provider: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []
    # Image generations started from this conversation. The client interleaves them with `messages`
    # by created_at to rebuild one timeline; they are kept as a separate list because a generation
    # is polled for completion while a message is already final.
    generations: list["GenerationRequestResponse"] = []


class CreateConversationRequest(BaseModel):
    """Opens an empty thread. Needed because a session can begin with an image generation rather
    than a message, and a generation has to belong to a conversation to be replayed in one."""

    title: str = Field(min_length=1, max_length=255)
    provider: str = Field(default="openai")

    @field_validator("provider")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in AVAILABLE_PROVIDERS:
            raise ValueError(f"Unknown provider: {value}")
        return value


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


from app.schemas.image import GenerationRequestResponse  # noqa: E402  circular at module top

ConversationDetailResponse.model_rebuild()
