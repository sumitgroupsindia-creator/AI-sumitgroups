from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Credit, UsageRecord


class InsufficientCreditsError(Exception):
    pass


async def get_or_create_credits(db: AsyncSession, user_id: UUID) -> Credit:
    result = await db.execute(select(Credit).where(Credit.user_id == user_id))
    credit = result.scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=user_id, chat_balance=0, image_balance=0)
        db.add(credit)
        await db.flush()
    return credit


async def reserve_credits(db: AsyncSession, user_id: UUID, kind: str, amount: int) -> None:
    """Atomically debit credits inside the caller's transaction. Raises InsufficientCreditsError
    (and leaves the transaction untouched) if the balance is too low. Uses a row lock to prevent
    concurrent requests from double-spending the same balance."""
    column = Credit.chat_balance if kind == "chat" else Credit.image_balance
    result = await db.execute(select(Credit).where(Credit.user_id == user_id).with_for_update())
    credit = result.scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=user_id, chat_balance=0, image_balance=0)
        db.add(credit)
        await db.flush()

    balance = credit.chat_balance if kind == "chat" else credit.image_balance
    if balance < amount:
        raise InsufficientCreditsError(f"Insufficient {kind} credits: have {balance}, need {amount}")

    if kind == "chat":
        credit.chat_balance -= amount
    else:
        credit.image_balance -= amount
    await db.flush()


async def refund_credits(db: AsyncSession, user_id: UUID, kind: str, amount: int) -> None:
    """Used when a reserved operation ultimately fails, so the user isn't charged for it."""
    result = await db.execute(select(Credit).where(Credit.user_id == user_id).with_for_update())
    credit = result.scalar_one_or_none()
    if credit is None:
        return
    if kind == "chat":
        credit.chat_balance += amount
    else:
        credit.image_balance += amount
    await db.flush()


async def record_usage(
    db: AsyncSession,
    *,
    user_id: UUID,
    request_id: str,
    provider: str,
    model: str,
    operation: str,
    credits_consumed: int,
    status: str,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    db.add(
        UsageRecord(
            user_id=user_id,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            credits_consumed=credits_consumed,
            status=status,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await db.flush()
