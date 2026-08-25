import time
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.chat import Conversation, Message
from app.models.image import ProviderConfig
from app.providers.base import ChatMessage, ProviderError
from app.providers.registry import get_chat_provider
from app.services.credit_service import (
    InsufficientCreditsError,
    record_usage,
    refund_credits,
    reserve_credits,
)

logger = get_logger("chat")

HISTORY_WINDOW = 20  # most recent messages sent as context


async def _get_credit_cost(db: AsyncSession, provider: str) -> int:
    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == provider, ProviderConfig.capability == "chat")
    )
    config = result.scalar_one_or_none()
    return config.credit_cost if config else 1


async def get_or_create_conversation(
    db: AsyncSession, user_id: UUID, conversation_id: UUID | None, provider: str, model: str, first_message: str
) -> Conversation:
    if conversation_id is not None:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation not found")
        return conversation

    conversation = Conversation(
        user_id=user_id,
        title=first_message[:60],
        provider=provider,
        model=model,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def stream_chat_message(
    *,
    user_id: UUID,
    conversation_id: UUID,
    user_message: str,
    provider_name: str,
    model: str,
    request_id: str,
) -> AsyncIterator[str]:
    """Opens its own DB session: the streaming body is consumed after the request-scoped session
    dependency has already been torn down, so it cannot borrow the endpoint's session."""
    async with AsyncSessionLocal() as db:
        async for chunk in _stream_chat_message(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            provider_name=provider_name,
            model=model,
            request_id=request_id,
        ):
            yield chunk


async def _stream_chat_message(
    db: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    user_message: str,
    provider_name: str,
    model: str,
    request_id: str,
) -> AsyncIterator[str]:
    cost = await _get_credit_cost(db, provider_name)

    try:
        await reserve_credits(db, user_id, "chat", cost)
    except InsufficientCreditsError:
        yield _sse_event("error", {"message": "Insufficient chat credits", "code": "insufficient_credits"})
        return
    await db.commit()

    db.add(Message(conversation_id=conversation_id, role="user", content=user_message))
    await db.commit()

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_WINDOW)
    )
    history = list(reversed(history_result.scalars().all()))
    provider_messages = [ChatMessage(role=m.role, content=m.content) for m in history]

    provider = get_chat_provider(provider_name)
    full_text = ""
    error_message: str | None = None
    started = time.perf_counter()

    try:
        async for chunk in provider.stream_chat(provider_messages, model):
            full_text += chunk
            yield _sse_event("delta", {"content": chunk})
    except ProviderError as exc:
        error_message = str(exc)
        logger.error("chat.provider_error", provider=provider_name, error=error_message, request_id=request_id)
        yield _sse_event("error", {"message": "The AI provider failed to respond. Please retry.", "code": "provider_error"})

    latency_ms = int((time.perf_counter() - started) * 1000)

    if full_text:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_text,
                provider=provider_name,
                model=model,
                error=error_message,
            )
        )
        await record_usage(
            db,
            user_id=user_id,
            request_id=request_id,
            provider=provider_name,
            model=model,
            operation="chat",
            credits_consumed=cost,
            status="success",
            latency_ms=latency_ms,
        )
    else:
        # Nothing generated — refund the reservation and log the failure without charging the user.
        await refund_credits(db, user_id, "chat", cost)
        await record_usage(
            db,
            user_id=user_id,
            request_id=request_id,
            provider=provider_name,
            model=model,
            operation="chat",
            credits_consumed=0,
            status="failed",
            latency_ms=latency_ms,
            error=error_message,
        )

    await db.commit()
    yield _sse_event("done", {"conversation_id": str(conversation_id)})


def _sse_event(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
