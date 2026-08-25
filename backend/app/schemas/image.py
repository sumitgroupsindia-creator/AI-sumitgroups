from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    providers: list[str] = Field(default_factory=lambda: ["openai", "gemini"])
    upload_file_id: UUID | None = None
    # Set when the generation was started from a conversation, so it can be replayed in that thread.
    conversation_id: UUID | None = None


class GenerationResultResponse(BaseModel):
    """User-facing shape. `provider` is kept because the client needs it as a stable slot key for
    regeneration, but the underlying vendor model id is deliberately omitted — the product presents
    neutral "Model 1 / Model 2" labels and must not leak which vendor sits behind each slot."""

    id: UUID
    provider: str
    status: str
    error: str | None
    image_url: str | None = None
    thumbnail_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminGenerationResultResponse(GenerationResultResponse):
    """Admins configure the providers, so they do see the real model id."""

    model: str


class GenerationRequestResponse(BaseModel):
    id: UUID
    prompt: str
    status: str
    conversation_id: UUID | None = None
    upload_file_id: UUID | None = None
    created_at: datetime
    results: list[GenerationResultResponse] = []

    model_config = {"from_attributes": True}


class RegenerateRequest(BaseModel):
    provider: str | None = None  # None = regenerate all providers on the original request


class UploadedFileResponse(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    width: int | None
    height: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
