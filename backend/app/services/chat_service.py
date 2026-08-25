import asyncio
import time
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.chat import Conversation, Message
from app.models.image import ProviderConfig, UploadedFile
from app.providers.base import ChatImage, ChatMessage, ProviderError
from app.providers.registry import get_chat_provider
from app.services.storage.local_storage import get_storage_provider
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


async def resolve_chat_model(db: AsyncSession, provider: str) -> str:
    """The model id an administrator configured for this slot.

    Chat used to read this from the environment while image generation read it from
    `provider_configs`, so editing a chat model in the admin panel silently did nothing. Both now
    resolve from the same row.
    """
    config = (
        await db.execute(
            select(ProviderConfig).where(
                ProviderConfig.provider == provider, ProviderConfig.capability == "chat"
            )
        )
    ).scalar_one_or_none()
    if config is None or not config.model:
        raise ValueError(f"No chat model configured for provider {provider}")
    return config.model


async def _load_attachment(db: AsyncSession, upload_file_id: UUID | None, user_id: UUID) -> ChatImage | None:
    """The image on this turn, or None. Scoped to the owner so an id cannot read someone else's upload."""
    if upload_file_id is None:
        return None
    uploaded = (
        await db.execute(
            select(UploadedFile).where(UploadedFile.id == upload_file_id, UploadedFile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if uploaded is None:
        return None
    try:
        data = await get_storage_provider().read("images/uploaded", uploaded.stored_filename)
    except FileNotFoundError:
        logger.warning("chat.attachment_missing", upload_file_id=str(upload_file_id))
        return None
    return ChatImage(data=data, mime_type=uploaded.content_type)


def _history_for(history: list[Message], provider_name: str) -> list[Message]:
    """Each model sees only its own side of the conversation.

    When two models answer the same turns, replaying both sets of answers to each of them would read
    as the model talking to itself and inventing things it never said. User turns are shared;
    assistant turns are filtered to the provider being asked.
    """
    return [m for m in history if m.role != "assistant" or m.provider == provider_name]


async def stream_chat_message(
    *,
    user_id: UUID,
    conversation_id: UUID,
    user_message: str,
    provider_names: list[str],
    upload_file_id: UUID | None,
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
            provider_names=provider_names,
            upload_file_id=upload_file_id,
            request_id=request_id,
        ):
            yield chunk


async def _stream_chat_message(
    db: AsyncSession,
    *,
    user_id: UUID,
    conversation_id: UUID,
    user_message: str,
    provider_names: list[str],
    upload_file_id: UUID | None,
    request_id: str,
) -> AsyncIterator[str]:
    costs = {name: await _get_credit_cost(db, name) for name in provider_names}

    # Reserved together: asking two models is one action to the user, and half an answer because the
    # second reservation failed would be worse than being told up front that it is unaffordable.
    try:
        await reserve_credits(db, user_id, "chat", sum(costs.values()))
    except InsufficientCreditsError:
        yield _sse_event(
            "error", {"provider": None, "message": "Insufficient chat credits", "code": "insufficient_credits"}
        )
        return
    await db.commit()

    db.add(
        Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            upload_file_id=upload_file_id,
        )
    )
    await db.commit()

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_WINDOW)
    )
    history = list(reversed(history_result.scalars().all()))

    image = await _load_attachment(db, upload_file_id, user_id)
    models = {name: await resolve_chat_model(db, name) for name in provider_names}

    # Each provider streams into a shared queue on its own task and its own DB session, so a slow
    # model never holds up a fast one and the client sees both answers fill in together.
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def run(name: str) -> None:
        try:
            await _run_provider(
                queue,
                user_id=user_id,
                conversation_id=conversation_id,
                provider_name=name,
                model=models[name],
                cost=costs[name],
                history=_history_for(history, name),
                image=image,
                request_id=request_id,
            )
        finally:
            await queue.put(None)  # this provider is finished, whatever happened

    tasks = [asyncio.create_task(run(name)) for name in provider_names]
    remaining = len(tasks)
    try:
        while remaining:
            item = await queue.get()
            if item is None:
                remaining -= 1
                continue
            yield item
    finally:
        # The client disconnected or the generator was closed: stop the providers rather than
        # leaving them streaming into a queue nobody reads.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    yield _sse_event("done", {"conversation_id": str(conversation_id)})


async def _run_provider(
    queue: "asyncio.Queue[str | None]",
    *,
    user_id: UUID,
    conversation_id: UUID,
    provider_name: str,
    model: str,
    cost: int,
    history: list[Message],
    image: ChatImage | None,
    request_id: str,
) -> None:
    # Only the current turn carries its image. Re-sending every past attachment would grow the
    # request without bound and re-bill the user for tokens they already paid for.
    last_index = len(history) - 1
    provider_messages = [
        ChatMessage(
            role=m.role,
            content=m.content,
            image=image if (i == last_index and m.role == "user") else None,
        )
        for i, m in enumerate(history)
    ]

    provider = get_chat_provider(provider_name)
    full_text = ""
    error_message: str | None = None
    started = time.perf_counter()

    async with AsyncSessionLocal() as db:
        try:
            async for chunk in provider.stream_chat(provider_messages, model):
                full_text += chunk
                await queue.put(_sse_event("delta", {"provider": provider_name, "content": chunk}))
        except ProviderError as exc:
            error_message = str(exc)
            logger.error(
                "chat.provider_error", provider=provider_name, error=error_message, request_id=request_id
            )
            await queue.put(
                _sse_event(
                    "error",
                    {
                        "provider": provider_name,
                        "message": "The AI provider failed to respond. Please retry.",
                        "code": "provider_error",
                    },
                )
            )

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
            # Nothing generated — refund this provider's share only; a sibling that succeeded keeps
            # its charge.
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

    await queue.put(_sse_event("provider_done", {"provider": provider_name}))


def _sse_event(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
