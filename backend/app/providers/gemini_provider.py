from typing import AsyncIterator

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.providers.base import ChatMessage, ChatProvider, ImageProvider, ImageResult, ProviderError

settings = get_settings()


class GeminiProvider(ChatProvider, ImageProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        history = [
            types.Content(role="user" if m.role == "user" else "model", parts=[types.Part(text=m.content)])
            for m in messages
        ]
        try:
            stream = await self._client.aio.models.generate_content_stream(model=model, contents=history)
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except (ClientError, ServerError) as exc:
            retryable = isinstance(exc, ServerError) or getattr(exc, "code", None) == 429
            raise ProviderError("gemini", f"Gemini error: {exc}", retryable=retryable) from exc
        except APIError as exc:
            raise ProviderError("gemini", "Gemini request failed", retryable=True) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(ProviderError),
        reraise=True,
    )
    async def generate_image(
        self, prompt: str, model: str, input_image: bytes | None = None, input_mime: str | None = None
    ) -> ImageResult:
        parts: list[types.Part] = [types.Part(text=prompt)]
        if input_image is not None:
            parts.insert(0, types.Part.from_bytes(data=input_image, mime_type=input_mime or "image/png"))

        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            for candidate in response.candidates or []:
                for part in candidate.content.parts or []:
                    if part.inline_data and part.inline_data.data:
                        return ImageResult(
                            image_bytes=part.inline_data.data,
                            content_type=part.inline_data.mime_type or "image/png",
                        )
            raise ProviderError("gemini", "Gemini returned no image data", retryable=False)
        except (ClientError, ServerError) as exc:
            retryable = isinstance(exc, ServerError) or getattr(exc, "code", None) == 429
            raise ProviderError("gemini", f"Gemini image error: {exc}", retryable=retryable) from exc
        except APIError as exc:
            raise ProviderError("gemini", "Gemini image request failed", retryable=True) from exc
