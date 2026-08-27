from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Credit, UsageRecord

# Amounts are Decimal throughout. A metered chat turn costs a fraction of a rupee, and an int would
# round every one of them — to zero, or to many times what it was worth.
Amount = Decimal | int


class InsufficientCreditsError(Exception):
    pass


def _as_decimal(amount: Amount) -> Decimal:
    return amount if isinstance(amount, Decimal) else Decimal(amount)


async def get_or_create_credits(db: AsyncSession, user_id: UUID) -> Credit:
    result = await db.execute(select(Credit).where(Credit.user_id == user_id))
    credit = result.scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=user_id, balance=Decimal(0))
        db.add(credit)
        await db.flush()
    return credit


async def _locked(db: AsyncSession, user_id: UUID) -> Credit:
    """The wallet row, locked for update. The lock is the whole point: two prompts sent at once
    would otherwise each read the same balance and both be allowed to spend it."""
    result = await db.execute(select(Credit).where(Credit.user_id == user_id).with_for_update())
    credit = result.scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=user_id, balance=Decimal(0))
        db.add(credit)
        await db.flush()
    return credit


async def reserve_credits(db: AsyncSession, user_id: UUID, amount: Amount) -> None:
    """Atomically debit the wallet inside the caller's transaction. Raises InsufficientCreditsError
    (and leaves the transaction untouched) if the balance is too low."""
    wanted = _as_decimal(amount)
    credit = await _locked(db, user_id)

    if credit.balance < wanted:
        raise InsufficientCreditsError(f"Insufficient credits: have {credit.balance}, need {wanted}")

    credit.balance -= wanted
    await db.flush()


async def refund_credits(db: AsyncSession, user_id: UUID, amount: Amount) -> None:
    """Used when a reserved operation ultimately fails, so the user isn't charged for it."""
    giving_back = _as_decimal(amount)
    credit = await _locked(db, user_id)
    credit.balance += giving_back
    await db.flush()


async def settle_credits(db: AsyncSession, user_id: UUID, *, reserved: Amount, actual: Amount) -> None:
    """Close out a reservation against what the operation really cost.

    A metered turn is charged before it runs, against a ceiling — nobody knows how long an answer
    will be until it has been written. This hands back the difference, or takes the shortfall if the
    answer somehow outran the ceiling.

    The balance is floored at zero on a shortfall rather than going negative. A wallet that was
    checked and found sufficient should not end the turn in debt over an estimate this system got
    wrong; the unbilled remainder is our error to absorb, and it still reaches the ledger as cost.
    """
    held = _as_decimal(reserved)
    owed = _as_decimal(actual)
    if held == owed:
        return

    credit = await _locked(db, user_id)
    difference = held - owed
    if difference > 0:
        credit.balance += difference  # over-reserved: give the remainder back
    else:
        credit.balance = max(Decimal(0), credit.balance + difference)
    await db.flush()


async def record_usage(
    db: AsyncSession,
    *,
    user_id: UUID,
    request_id: str,
    provider: str,
    model: str,
    operation: str,
    credits_consumed: Amount,
    status: str,
    cost_inr: Decimal = Decimal(0),
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    """One line in the ledger. `cost_inr` is what the vendor billed us, so the margin report can be
    built from what actually happened rather than from today's prices; a failed operation records
    zero on both sides, since the customer was refunded and nothing was delivered.

    The token counts are the vendor's own, when it reported any. They are what makes a metered
    charge auditable: without them the ledger asserts an amount with nothing behind it.
    """
    db.add(
        UsageRecord(
            user_id=user_id,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            credits_consumed=_as_decimal(credits_consumed),
            cost_inr=cost_inr,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error=error,
        )
    )
    await db.flush()
