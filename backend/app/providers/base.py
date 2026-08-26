from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Literal


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


# What the product asks a model for, beyond the customer's own turn. Portrait is the default
# because almost everything made here is posted to a phone.
Aspect = Literal["portrait", "square", "landscape"]


class ChatProvider(ABC):
    name: str

    @abstractmethod
    async def stream_chat(
        self, messages: list[ChatMessage], model: str, system: str | None = None
    ) -> AsyncIterator[str]:
        """Yield incremental text chunks. `system` carries the product's standing instructions."""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    async def complete(
        self, messages: list[ChatMessage], model: str, system: str | None = None, max_tokens: int = 256
    ) -> str:
        """One short answer, all at once.

        Used by the machinery rather than by the customer — routing a request to a style, reading an
        attached photo — where there is nothing to stream to and the reply is a few tokens. Capped,
        because an unbounded answer to a question expecting "3" is pure cost.
        """
        raise NotImplementedError


class ImageProvider(ABC):
    name: str

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        model: str,
        input_image: bytes | None = None,
        input_mime: str | None = None,
        aspect: Aspect = "portrait",
    ) -> ImageResult:
        """Generate (or edit, when input_image is provided) an image from a prompt."""
        raise NotImplementedError
