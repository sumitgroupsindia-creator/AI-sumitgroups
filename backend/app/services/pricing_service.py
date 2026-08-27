"""What one AI operation costs us, and what it costs the customer.

One credit is one rupee, and one rule covers everything:

    charge = what the vendor billed us  +  a flat margin

The margin is a plain number of credits rather than a percentage, so an administrator reads it as
rupees earned on that operation — 0.5 on a chat turn, 3 on a picture. What differs between
capabilities is only how the vendor's bill is arrived at:

**Metered** (chat). The bill is built from the token counts the vendor itself reports, at
per-million-token rates. A turn has no fixed size, so any flat figure would be an average, and an
average is wrong in both directions — a one-line reply would subsidise an essay.

**Flat** (images). One prompt buys one picture and the vendor bills the same whether it took two
words to ask for or two hundred, so `provider_cost_inr` *is* the bill.

A slot is metered when it has token rates and flat when it does not. Nothing else selects between
them, and the margin is added the same way either way.

Every price is resolved here and nowhere else, so a reservation, a refund and the number quoted in
an admin screen cannot drift apart — which they previously could, since the reservation and the
refund each looked the cost up separately. Margin is charged per generated image rather than per
prompt: asking both slots produces two pictures and two vendor bills, so it has to produce two
margins as well, and it keeps refunds honest because what is handed back when one slot fails is
exactly what that slot was charged.
"""

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import ProviderConfig
from app.providers.base import TokenUsage

# Used only when a provider has no row at all — a misconfiguration should make an operation
# expensive, never free, so a missing row cannot be a way to generate images for nothing.
_FALLBACK_MARGIN = {"chat": Decimal("0.5"), "image": Decimal(3)}
_FALLBACK_COST_INR = {"chat": Decimal("0.10"), "image": Decimal("4.00")}

_PER_MILLION = Decimal(1_000_000)
_PAISE = Decimal("0.0001")

# What a turn is assumed to cost before it has happened.
#
# The reservation is a ceiling, not a prediction: it is taken before the model answers and settled
# against the real counts the moment it stops. Being generous here costs the customer nothing — the
# difference comes straight back — while being stingy would let a long answer overdraw a wallet that
# was checked and found sufficient.
RESERVE_OUTPUT_TOKENS = 2_000
# An attached photo is worth roughly this many input tokens to either vendor. Rough on purpose: it
# only has to be large enough that the reservation covers the real figure.
IMAGE_INPUT_TOKENS = 1_500
# Roughly four characters to a token, across both tokenizers, for English and for Hinglish. Used
# only to size a reservation, never to bill.
CHARS_PER_TOKEN = 4

# What a middling turn looks like, for reporting a representative price in the admin screens.
TYPICAL_INPUT_TOKENS = 700
TYPICAL_OUTPUT_TOKENS = 400


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(_PAISE, rounding=ROUND_HALF_UP)


def estimate_tokens(text: str) -> int:
    """A cheap character-count approximation. Sizes reservations; never bills."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass(frozen=True)
class Price:
    """The full economics of one operation on one provider slot."""

    provider: str
    capability: str
    model: str
    # What the vendor bills for one flat-priced operation, in rupees. Unused when metered.
    cost_inr: Decimal
    # Flat credits added on top of the vendor's bill. This is the profit.
    margin_credits: Decimal
    input_rate_inr: Decimal = Decimal(0)   # rupees per million input tokens
    output_rate_inr: Decimal = Decimal(0)  # rupees per million output tokens
    # Applied to the vendor's bill before the margin is added. 1.000 passes the cost through
    # untouched, which is the default; raising it marks the cost itself up as well.
    markup: Decimal = Decimal(1)

    @property
    def metered(self) -> bool:
        """True when this slot is billed on real token counts rather than per operation."""
        return self.input_rate_inr > 0 or self.output_rate_inr > 0

    # ------------------------------------------------------------------ flat

    @property
    def credits(self) -> Decimal:
        """What one flat-priced operation charges: the vendor's bill plus the margin.

        Meaningless for a metered slot, where the bill depends on the answer — use `charge_for`.
        """
        return _round(self.cost_inr * self.markup) + self.margin_credits

    @property
    def revenue_inr(self) -> Decimal:
        """Credits are rupees, so revenue is the charge itself."""
        return self.credits

    @property
    def profit_inr(self) -> Decimal:
        return self.revenue_inr - self.cost_inr

    # --------------------------------------------------------------- metered

    def vendor_cost_for(self, input_tokens: int, output_tokens: int) -> Decimal:
        """What the vendor bills us for this many tokens, in rupees."""
        billed = (
            Decimal(input_tokens) * self.input_rate_inr
            + Decimal(output_tokens) * self.output_rate_inr
        ) / _PER_MILLION
        return _round(billed)

    def charge_for(self, input_tokens: int, output_tokens: int) -> Decimal:
        """What the customer pays for this many tokens, in credits."""
        return _round(self.vendor_cost_for(input_tokens, output_tokens) * self.markup) + self.margin_credits

    # ------------------------------------------------------------ either way

    def settle(self, usage: TokenUsage) -> tuple[Decimal, Decimal]:
        """`(credits to charge, what it cost us)` for one completed call.

        A vendor that reported nothing falls back to the flat price. Silence is not the same as zero
        tokens, and treating it as zero would hand out answers for the margin alone whenever a
        vendor changed its response shape — the failure mode should be a slightly wrong bill, never
        a free model call.
        """
        if not self.metered or not usage.reported:
            return self.credits, self.cost_inr
        return (
            self.charge_for(usage.input_tokens, usage.output_tokens),
            self.vendor_cost_for(usage.input_tokens, usage.output_tokens),
        )

    def reservation_for(self, prompt_chars: int, has_image: bool = False) -> Decimal:
        """The ceiling held before the model answers, in credits.

        Priced against the longest answer the turn could produce, so a wallet that passed the check
        cannot be overdrawn by the reply that follows. Whatever is not used is returned the instant
        the answer ends.
        """
        if not self.metered:
            return self.credits
        input_tokens = (prompt_chars // CHARS_PER_TOKEN) + (IMAGE_INPUT_TOKENS if has_image else 0)
        return self.charge_for(max(input_tokens, 1), RESERVE_OUTPUT_TOKENS)

    @property
    def typical_credits(self) -> Decimal:
        """A representative price for one operation.

        Flat slots charge exactly this. Metered slots cannot be quoted exactly — the price depends
        on an answer nobody has read yet — so this is what a middling turn comes to, which is what
        the admin screens report alongside the margin.
        """
        if not self.metered:
            return self.credits
        return self.charge_for(TYPICAL_INPUT_TOKENS, TYPICAL_OUTPUT_TOKENS)

    @property
    def typical_cost_inr(self) -> Decimal:
        """What that same representative operation costs us."""
        if not self.metered:
            return self.cost_inr
        return self.vendor_cost_for(TYPICAL_INPUT_TOKENS, TYPICAL_OUTPUT_TOKENS)


def from_config(config: ProviderConfig) -> Price:
    return Price(
        provider=config.provider,
        capability=config.capability,
        model=config.model,
        cost_inr=Decimal(config.provider_cost_inr),
        margin_credits=Decimal(config.margin_credits),
        input_rate_inr=Decimal(config.input_cost_per_mtok_inr),
        output_rate_inr=Decimal(config.output_cost_per_mtok_inr),
        markup=Decimal(config.markup_multiplier),
    )


def fallback(provider: str, capability: str) -> Price:
    """No row at all. Deliberately flat and deliberately expensive: a missing configuration must
    never be the cheap path."""
    return Price(
        provider=provider,
        capability=capability,
        model=provider,
        cost_inr=_FALLBACK_COST_INR.get(capability, Decimal("4.00")),
        margin_credits=_FALLBACK_MARGIN.get(capability, Decimal(3)),
    )


def with_margin(price: Price, margin: Decimal) -> Price:
    """The same price with a different margin. Used by tests and by what-if reporting."""
    return replace(price, margin_credits=margin)


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


async def quote(db: AsyncSession, providers: list[str], capability: str) -> Decimal:
    """What one prompt across these slots is expected to cost the customer, in credits."""
    prices = await load(db, capability)
    return sum(
        ((prices.get(p) or fallback(p, capability)).typical_credits for p in providers),
        Decimal(0),
    )
