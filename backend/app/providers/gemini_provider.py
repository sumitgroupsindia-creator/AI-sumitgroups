from functools import lru_cache
from typing import AsyncIterator

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.providers.base import (
    Aspect,
    ChatMessage,
    ChatProvider,
    ImageProvider,
    ImageResult,
    ProviderError,
)
from app.services import settings_service


@lru_cache(maxsize=4)
def _client_for(api_key: str) -> genai.Client:
    """One client per distinct key, so a key rotated in the admin UI takes effect without a restart."""
    return genai.Client(api_key=api_key)


def _to_gemini_parts(message: ChatMessage) -> list[types.Part]:
    """The image goes first: Gemini attends to it as context for the text that follows."""
    parts: list[types.Part] = []
    if message.image is not None:
        parts.append(types.Part.from_bytes(data=message.image.data, mime_type=message.image.mime_type))
    parts.append(types.Part(text=message.content))
    return parts


def _to_history(messages: list[ChatMessage]) -> list[types.Content]:
    """Gemini has only `user` and `model` turns; standing instructions travel separately."""
    return [
        types.Content(role="user" if m.role == "user" else "model", parts=_to_gemini_parts(m))
        for m in messages
        if m.role != "system"
    ]


def _config(system: str | None, max_tokens: int | None = None) -> types.GenerateContentConfig | None:
    if not system and max_tokens is None:
        return None
    return types.GenerateContentConfig(
        system_instruction=system or None,
        max_output_tokens=max_tokens,
    )


class GeminiProvider(ChatProvider, ImageProvider):
    name = "gemini"

    async def _client(self) -> genai.Client:
        return _client_for(await settings_service.get_str("gemini_api_key"))

    async def stream_chat(
        self, messages: list[ChatMessage], model: str, system: str | None = None
    ) -> AsyncIterator[str]:
        try:
            client = await self._client()
            stream = await client.aio.models.generate_content_stream(
                model=model, contents=_to_history(messages), config=_config(system)
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except (ClientError, ServerError) as exc:
            retryable = isinstance(exc, ServerError) or getattr(exc, "code", None) == 429
            raise ProviderError("gemini", f"Gemini error: {exc}", retryable=retryable) from exc
        except APIError as exc:
            raise ProviderError("gemini", "Gemini request failed", retryable=True) from exc

    async def complete(
        self, messages: list[ChatMessage], model: str, system: str | None = None, max_tokens: int = 256
    ) -> str:
        try:
            response = await (await self._client()).aio.models.generate_content(
                model=model,
                contents=_to_history(messages),
                config=_config(system, max_tokens=max_tokens),
            )
            return (response.text or "").strip()
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
        self,
        prompt: str,
        model: str,
        input_image: bytes | None = None,
        input_mime: str | None = None,
        aspect: Aspect = "portrait",
    ) -> ImageResult:
        # No size parameter on this SDK version, so the shape has to be asked for in words. The
        # caller has already put the aspect into the prompt; `aspect` is accepted here so both
        # providers present the same interface.
        del aspect
        parts: list[types.Part] = [types.Part(text=prompt)]
        if input_image is not None:
            parts.insert(0, types.Part.from_bytes(data=input_image, mime_type=input_mime or "image/png"))

        try:
            response = await (await self._client()).aio.models.generate_content(
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
