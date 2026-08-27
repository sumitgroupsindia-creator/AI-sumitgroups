import asyncio
import time
from decimal import Decimal
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.chat import Conversation, Message
from app.models.image import ProviderConfig, UploadedFile
from app.providers.base import ChatImage, ChatMessage, ProviderError, TokenUsage
from app.providers.registry import get_chat_provider
from app.services.storage.local_storage import get_storage_provider
from app.services import pricing_service, prompt_service
from app.services.credit_service import (
    InsufficientCreditsError,
    record_usage,
    refund_credits,
    reserve_credits,
    settle_credits,
)
from app.services.pricing_service import Price

logger = get_logger("chat")

HISTORY_WINDOW = 20  # most recent messages sent as context


class _Hold:
    """One provider's reservation, and whether anything has been done about it yet.

    The wallet is debited before a model runs, so every path out of that model — answered, refused,
    crashed, cancelled — owes the customer either a charge or a refund. This flag is what lets the
    outer guard tell "already settled" from "nobody settled this", so a hold is released once and
    never twice.
    """

    __slots__ = ("amount", "settled")

    def __init__(self, amount: Decimal) -> None:
        self.amount = amount
        self.settled = False


async def _price(db: AsyncSession, provider: str) -> Price:
    return await pricing_service.price_for(db, provider, "chat")


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
    prices = {name: await _price(db, name) for name in provider_names}

    # What is held before a word is generated. On a metered slot this is a ceiling priced against
    # the longest answer the turn could produce, not a prediction — whatever is not used comes back
    # the moment the answer ends. Reserving the real figure is impossible: nobody knows how long an
    # answer is until it has been written.
    holds = {
        name: _Hold(price.reservation_for(len(user_message), has_image=upload_file_id is not None))
        for name, price in prices.items()
    }

    # Reserved together: asking two models is one action to the user, and half an answer because the
    # second reservation failed would be worse than being told up front that it is unaffordable.
    try:
        await reserve_credits(db, user_id, sum((h.amount for h in holds.values()), Decimal(0)))
    except InsufficientCreditsError:
        yield _sse_event(
            "error",
            {"provider": None, "message": "क्रेडिट ख़त्म हो गए हैं।", "code": "insufficient_credits"},
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

    # Composed once for the turn, not once per slot: both models are answering the same request, so
    # they get the same standing instructions — and routing it twice would pay for the same answer
    # twice.
    composed = await prompt_service.compose_chat(
        db, user_message, user_id=user_id, request_id=request_id, provider=provider_names[0]
    )

    # Each provider streams into a shared queue on its own task and its own DB session, so a slow
    # model never holds up a fast one and the client sees both answers fill in together.
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def run(name: str) -> None:
        """One provider, and a guarantee that its reservation does not vanish.

        `_run_provider` settles the hold itself on every path it can see. This wrapper exists for
        the paths it cannot: the client disconnecting mid-answer, or the session failing before the
        ledger could be written. Without it an exception here is swallowed whole by the
        `return_exceptions=True` gather below — no log, no refund, and the customer has paid for
        an answer that was never delivered.
        """
        try:
            await _run_provider(
                queue,
                user_id=user_id,
                conversation_id=conversation_id,
                provider_name=name,
                model=models[name],
                price=prices[name],
                hold=holds[name],
                history=_history_for(history, name),
                image=image,
                system=composed.system,
                request_id=request_id,
            )
        except asyncio.CancelledError:
            await _release(user_id, holds[name], provider=name, request_id=request_id)
            raise
        except Exception:
            logger.exception("chat.provider_crashed", provider=name, request_id=request_id)
            await _release(user_id, holds[name], provider=name, request_id=request_id)
            await queue.put(
                _sse_event(
                    "error",
                    {
                        "provider": name,
                        "message": "The AI provider failed to respond. Please retry.",
                        "code": "provider_error",
                    },
                )
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


async def _release(user_id: UUID, hold: "_Hold", *, provider: str, request_id: str) -> None:
    """Hand back a reservation nothing else has accounted for.

    Opens its own session because the one that should have done this is, by definition, gone. Never
    raises: this runs on the failure path, and a bookkeeping error here would replace a refund with
    a second crash.
    """
    if hold.settled:
        return
    hold.settled = True
    try:
        async with AsyncSessionLocal() as db:
            await refund_credits(db, user_id, hold.amount)
            await db.commit()
    except Exception:
        logger.exception("chat.hold_not_released", provider=provider, request_id=request_id)


async def _run_provider(
    queue: "asyncio.Queue[str | None]",
    *,
    user_id: UUID,
    conversation_id: UUID,
    provider_name: str,
    model: str,
    price: Price,
    hold: "_Hold",
    history: list[Message],
    image: ChatImage | None,
    system: str,
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
    # Filled in by the provider as the answer arrives; read once it has finished, whether it
    # finished by completing or by failing. A turn that broke off half way still burned the tokens
    # it had already generated, and the vendor bills us for those.
    usage = TokenUsage()

    async with AsyncSessionLocal() as db:
        try:
            async for chunk in provider.stream_chat(
                provider_messages, model, system=system or None, usage=usage
            ):
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
        except Exception as exc:
            # A vendor SDK that raises something its own error hierarchy does not cover — a bad
            # key, a changed method signature, a malformed response. Caught here so it lands on
            # the refund-and-record path below like any other failure, rather than escaping and
            # taking the customer's reservation with it.
            error_message = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "chat.provider_unhandled", provider=provider_name, request_id=request_id
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
            # What the answer actually cost, from the vendor's own token counts. `settle` falls
            # back to the flat configured price when the vendor reported nothing, so a silent
            # provider produces a slightly wrong bill rather than a free one.
            charge, cost_inr = price.settle(usage)

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
            # The reservation was a ceiling. This is where the difference goes back.
            hold.settled = True
            await settle_credits(db, user_id, reserved=hold.amount, actual=charge)
            await record_usage(
                db,
                user_id=user_id,
                request_id=request_id,
                provider=provider_name,
                model=model,
                operation="chat",
                credits_consumed=charge,
                cost_inr=cost_inr,
                input_tokens=usage.input_tokens if usage.reported else None,
                output_tokens=usage.output_tokens if usage.reported else None,
                status="success",
                latency_ms=latency_ms,
            )
        else:
            # Nothing generated — refund this provider's whole hold; a sibling that succeeded keeps
            # its charge. The customer pays for answers, not for attempts.
            hold.settled = True
            await refund_credits(db, user_id, hold.amount)
            await record_usage(
                db,
                user_id=user_id,
                request_id=request_id,
                provider=provider_name,
                model=model,
                operation="chat",
                credits_consumed=Decimal(0),
                status="failed",
                input_tokens=usage.input_tokens if usage.reported else None,
                output_tokens=usage.output_tokens if usage.reported else None,
                latency_ms=latency_ms,
                error=error_message,
            )

        await db.commit()

    await queue.put(_sse_event("provider_done", {"provider": provider_name}))


def _sse_event(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
