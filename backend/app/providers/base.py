from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ChatImage:
    """An image the user attached to a chat turn, for the model to look at."""

    data: bytes
    mime_type: str


@dataclass
class ChatMessage:
    role: str  # user | assistant | system
    content: str
    image: ChatImage | None = None


@dataclass
class ImageResult:
    image_bytes: bytes
    content_type: str = "image/png"
    revised_prompt: str | None = None


class ProviderError(Exception):
    """Raised for any provider failure; the caller decides how to surface it (never raw to the client)."""

    def __init__(self, provider: str, message: str, retryable: bool = False):
        self.provider = provider
        self.retryable = retryable
        super().__init__(message)


class ChatProvider(ABC):
    name: str

    @abstractmethod
    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        """Yield incremental text chunks."""
        raise NotImplementedError
        yield  # pragma: no cover


class ImageProvider(ABC):
    name: str

    @abstractmethod
    async def generate_image(
        self, prompt: str, model: str, input_image: bytes | None = None, input_mime: str | None = None
    ) -> ImageResult:
        """Generate (or edit, when input_image is provided) an image from a prompt."""
        raise NotImplementedError
