from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    providers: list[str] = Field(default_factory=lambda: ["openai", "gemini"])
    upload_file_id: UUID | None = None


class GenerationResultResponse(BaseModel):
    id: UUID
    provider: str
    model: str
    status: str
    error: str | None
    image_url: str | None = None
    thumbnail_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerationRequestResponse(BaseModel):
    id: UUID
    prompt: str
    status: str
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
