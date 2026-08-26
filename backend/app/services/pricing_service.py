"""What one AI operation costs us, and what it costs the customer.

One credit is one rupee. What a vendor bills us is held in rupees on `provider_configs`; the
customer pays `credit_cost + margin_credits`; the difference is the margin. Every price is resolved
here and nowhere else, so a reservation, a refund and the number quoted in the UI cannot drift apart
— which they previously could, since the reservation and the refund each looked the cost up
separately.

Margin is charged per generated image rather than per prompt. Asking both slots produces two
pictures and two vendor bills, so it has to produce two margins as well; it also keeps refunds
honest, because what is handed back when one slot fails is exactly what that slot was charged.
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import ProviderConfig

# Used only when a provider has no row at all — a misconfiguration should make an operation
# expensive, never free, so a missing row cannot be a way to generate images for nothing.
_FALLBACK_BASE = {"chat": 1, "image": 5}
_FALLBACK_MARGIN = {"chat": 0, "image": 3}
_FALLBACK_COST_INR = {"chat": Decimal("0.10"), "image": Decimal("4.00")}


@dataclass(frozen=True)
class Price:
    """The full economics of one operation on one provider slot."""

    provider: str
    capability: str
    model: str
    base_credits: int
    margin_credits: int
    cost_inr: Decimal

    @property
    def credits(self) -> int:
        """What the customer is charged. Reserved, refunded and displayed as this one number."""
        return self.base_credits + self.margin_credits

    @property
    def revenue_inr(self) -> Decimal:
        """Credits are rupees, so revenue is the charge itself."""
        return Decimal(self.credits)

    @property
    def profit_inr(self) -> Decimal:
        return self.revenue_inr - self.cost_inr


def from_config(config: ProviderConfig) -> Price:
    return Price(
        provider=config.provider,
        capability=config.capability,
        model=config.model,
        base_credits=config.credit_cost,
        margin_credits=config.margin_credits,
        cost_inr=Decimal(config.provider_cost_inr),
    )


def fallback(provider: str, capability: str) -> Price:
    return Price(
        provider=provider,
        capability=capability,
        model=provider,
        base_credits=_FALLBACK_BASE.get(capability, 5),
        margin_credits=_FALLBACK_MARGIN.get(capability, 3),
        cost_inr=_FALLBACK_COST_INR.get(capability, Decimal("4.00")),
    )


async def load(db: AsyncSession, capability: str) -> dict[str, Price]:
    """Every configured price for one capability, keyed by provider."""
    rows = (
        await db.execute(select(ProviderConfig).where(ProviderConfig.capability == capability))
    ).scalars().all()
    return {row.provider: from_config(row) for row in rows}


async def price_for(db: AsyncSession, provider: str, capability: str) -> Price:
    row = (
        await db.execute(
            select(ProviderConfig).where(
                ProviderConfig.provider == provider, ProviderConfig.capability == capability
            )
        )
    ).scalar_one_or_none()
    return from_config(row) if row is not None else fallback(provider, capability)


async def quote(db: AsyncSession, providers: list[str], capability: str) -> int:
    """What one prompt across these slots will cost the customer, in credits."""
    prices = await load(db, capability)
    return sum((prices.get(p) or fallback(p, capability)).credits for p in providers)
