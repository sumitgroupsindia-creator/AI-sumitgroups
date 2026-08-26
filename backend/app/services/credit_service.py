from decimal import Decimal
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
        credit = Credit(user_id=user_id, balance=0)
        db.add(credit)
        await db.flush()
    return credit


async def reserve_credits(db: AsyncSession, user_id: UUID, amount: int) -> None:
    """Atomically debit the wallet inside the caller's transaction. Raises InsufficientCreditsError
    (and leaves the transaction untouched) if the balance is too low. Uses a row lock to prevent
    concurrent requests from double-spending the same balance."""
    result = await db.execute(select(Credit).where(Credit.user_id == user_id).with_for_update())
    credit = result.scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=user_id, balance=0)
        db.add(credit)
        await db.flush()

    if credit.balance < amount:
        raise InsufficientCreditsError(f"Insufficient credits: have {credit.balance}, need {amount}")

    credit.balance -= amount
    await db.flush()


async def refund_credits(db: AsyncSession, user_id: UUID, amount: int) -> None:
    """Used when a reserved operation ultimately fails, so the user isn't charged for it."""
    result = await db.execute(select(Credit).where(Credit.user_id == user_id).with_for_update())
    credit = result.scalar_one_or_none()
    if credit is None:
        return
    credit.balance += amount
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
    cost_inr: Decimal = Decimal(0),
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    """One line in the ledger. `cost_inr` is what the vendor billed us, so the margin report can be
    built from what actually happened rather than from today's prices; a failed operation records
    zero on both sides, since the customer was refunded and no image was delivered."""
    db.add(
        UsageRecord(
            user_id=user_id,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            credits_consumed=credits_consumed,
            cost_inr=cost_inr,
            status=status,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await db.flush()
