import base64
from functools import lru_cache
from typing import AsyncIterator

from openai import APIError, APIStatusError, APITimeoutError, AsyncOpenAI
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
def _client_for(api_key: str) -> AsyncOpenAI:
    """One client per distinct key. Rotating the key in the admin UI produces a new client on the
    next call and lets the old one fall out of the cache, so no restart is needed."""
    return AsyncOpenAI(api_key=api_key, timeout=60.0)


def _to_openai_message(message: ChatMessage) -> dict:
    """Plain string content unless the turn carries an image, which OpenAI takes as content parts."""
    if message.image is None:
        return {"role": message.role, "content": message.content}
    encoded = base64.b64encode(message.image.data).decode()
    return {
        "role": message.role,
        "content": [
            {"type": "text", "text": message.content},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{message.image.mime_type};base64,{encoded}"},
            },
        ],
    }


# gpt-image-1's supported sizes. Portrait is 2:3 rather than a true 9:16 — the closest the API
# offers — so the prompt still asks for a mobile composition on top of this.
_SIZES: dict[str, str] = {
    "portrait": "1024x1536",
    "square": "1024x1024",
    "landscape": "1536x1024",
}


def _with_system(messages: list[ChatMessage], system: str | None) -> list[dict]:
    """OpenAI takes standing instructions as a system message at the head of the list."""
    head = [{"role": "system", "content": system}] if system else []
    return head + [_to_openai_message(m) for m in messages]


class OpenAIProvider(ChatProvider, ImageProvider):
    name = "openai"

    async def _client(self) -> AsyncOpenAI:
        return _client_for(await settings_service.get_str("openai_api_key"))

    async def stream_chat(
        self, messages: list[ChatMessage], model: str, system: str | None = None
    ) -> AsyncIterator[str]:
        try:
            client = await self._client()
            stream = await client.chat.completions.create(
                model=model,
                messages=_with_system(messages, system),
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

    async def complete(
        self, messages: list[ChatMessage], model: str, system: str | None = None, max_tokens: int = 256
    ) -> str:
        try:
            result = await (await self._client()).chat.completions.create(
                model=model,
                messages=_with_system(messages, system),
                max_tokens=max_tokens,
            )
            return (result.choices[0].message.content or "").strip() if result.choices else ""
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
        self,
        prompt: str,
        model: str,
        input_image: bytes | None = None,
        input_mime: str | None = None,
        aspect: Aspect = "portrait",
    ) -> ImageResult:
        size = _SIZES.get(aspect, _SIZES["portrait"])
        try:
            if input_image is not None:
                result = await (await self._client()).images.edit(
                    model=model,
                    image=("input.png", input_image, input_mime or "image/png"),
                    prompt=prompt,
                    size=size,
                )
            else:
                result = await (await self._client()).images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
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
