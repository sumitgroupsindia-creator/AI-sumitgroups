from functools import lru_cache

from app.providers.base import ChatProvider, ImageProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider


@lru_cache
def _instances() -> dict[str, OpenAIProvider | GeminiProvider]:
    return {"openai": OpenAIProvider(), "gemini": GeminiProvider()}


def get_chat_provider(name: str) -> ChatProvider:
    provider = _instances().get(name)
    if provider is None:
        raise ValueError(f"Unknown chat provider: {name}")
    return provider


def get_image_provider(name: str) -> ImageProvider:
    provider = _instances().get(name)
    if provider is None:
        raise ValueError(f"Unknown image provider: {name}")
    return provider


AVAILABLE_PROVIDERS = ("openai", "gemini")
