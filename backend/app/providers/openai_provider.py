import base64
from typing import AsyncIterator

from openai import APIError, APIStatusError, APITimeoutError, AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.providers.base import ChatMessage, ChatProvider, ImageProvider, ImageResult, ProviderError

settings = get_settings()


class OpenAIProvider(ChatProvider, ImageProvider):
    name = "openai"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=60.0)

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except APITimeoutError as exc:
            raise ProviderError("openai", "OpenAI request timed out", retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code in (429, 500, 502, 503, 504)
            raise ProviderError("openai", f"OpenAI error: {exc.status_code}", retryable=retryable) from exc
        except APIError as exc:
            raise ProviderError("openai", "OpenAI request failed", retryable=True) from exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(ProviderError),
        reraise=True,
    )
    async def generate_image(
        self, prompt: str, model: str, input_image: bytes | None = None, input_mime: str | None = None
    ) -> ImageResult:
        try:
            if input_image is not None:
                result = await self._client.images.edit(
                    model=model,
                    image=("input.png", input_image, input_mime or "image/png"),
                    prompt=prompt,
                    size="1024x1024",
                )
            else:
                result = await self._client.images.generate(
                    model=model,
                    prompt=prompt,
                    size="1024x1024",
                    n=1,
                )
            b64 = result.data[0].b64_json
            revised = getattr(result.data[0], "revised_prompt", None)
            return ImageResult(image_bytes=base64.b64decode(b64), content_type="image/png", revised_prompt=revised)
        except APITimeoutError as exc:
            raise ProviderError("openai", "OpenAI image request timed out", retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code in (429, 500, 502, 503, 504)
            raise ProviderError("openai", f"OpenAI image error: {exc.status_code}", retryable=retryable) from exc
        except APIError as exc:
            raise ProviderError("openai", "OpenAI image request failed", retryable=True) from exc
