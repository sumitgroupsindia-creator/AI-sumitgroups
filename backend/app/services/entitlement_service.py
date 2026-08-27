"""Which model slots an account is allowed to use.

Separate from pricing because it answers a different question. Pricing asks *what does this cost*;
this asks *may they have it at all*. A free account has credits and can spend them — just not on
every slot.

Enforced here, on the server, rather than only by hiding buttons. The composer does hide them, but
`providers` is a field in a JSON body that anyone can edit, so a gate that lived only in the browser
would be a suggestion.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Plan, Subscription
from app.models.settings import ProviderBrand


class PlanNotEntitledError(Exception):
    """Raised when an account asks for a slot its plan does not include."""

    def __init__(self, providers: list[str]):
        self.providers = providers
        super().__init__("This model needs a paid plan")


async def has_paid_plan(db: AsyncSession, user_id: UUID) -> bool:
    """True when the account is on an active, non-zero-priced plan.

    Judged by price rather than by plan code: `code == 'free'` breaks the moment someone adds a
    second free tier or renames one, while a plan that costs nothing is unambiguous. A subscription
    that is pending, past_due, cancelled or expired does not count — only one that is active right
    now buys anything.
    """
    row = (
        await db.execute(
            select(Plan.price)
            .join(Subscription, Subscription.plan_id == Plan.id)
            .where(Subscription.user_id == user_id, Subscription.status == "active")
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None and row > 0


async def paid_only_providers(db: AsyncSession) -> set[str]:
    rows = (
        await db.execute(
            select(ProviderBrand.provider).where(ProviderBrand.requires_paid_plan.is_(True))
        )
    ).scalars().all()
    return set(rows)


async def check_allowed(db: AsyncSession, user_id: UUID, providers: list[str]) -> None:
    """Raises PlanNotEntitledError if any requested slot is beyond this account's plan.

    Asking for both slots is not gated separately — it is gated because it contains the premium one,
    which is the same rule stated once instead of twice.
    """
    restricted = await paid_only_providers(db)
    wanted = restricted.intersection(providers)
    if not wanted:
        return
    if await has_paid_plan(db, user_id):
        return
    raise PlanNotEntitledError(sorted(wanted))
