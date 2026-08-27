"""What one AI operation costs us, and what it costs the customer.

One credit is one rupee. Every price is resolved here and nowhere else, so a reservation, a refund
and the number quoted in the UI cannot drift apart — which they previously could, since the
reservation and the refund each looked the cost up separately.

There are two ways a slot is priced, and which one applies is a property of the work, not a setting
somebody chose:

**Flat, per operation.** Image generation. One prompt buys one picture at one price, and the vendor
bills the same whether the picture took two words to ask for or two hundred. `provider_cost_inr` is
what they bill, `credit_cost + margin_credits` is what the customer pays, and the difference is the
margin. Margin is charged per generated image rather than per prompt: asking both slots produces
two pictures and two vendor bills, so it has to produce two margins as well — and it keeps refunds
honest, because what is handed back when one slot fails is exactly what that slot was charged.

**Metered, per token.** Chat. A turn has no fixed size, so a flat price can only ever be an average,
and an average is wrong in both directions — a one-line reply subsidises an essay. When a slot
carries token rates, the charge is built from the token counts the vendor itself reports, times a
markup. The margin is a multiplier rather than a flat number of credits because a bill that scales
with the answer needs a margin that scales with it too.

A slot is metered when it has rates, and flat when it does not. Nothing else selects between them.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import ProviderConfig
from app.providers.base import TokenUsage

# Used only when a provider has no row at all — a misconfiguration should make an operation
# expensive, never free, so a missing row cannot be a way to generate images for nothing.
_FALLBACK_BASE = {"chat": 1, "image": 5}
_FALLBACK_MARGIN = {"chat": 0, "image": 3}
_FALLBACK_COST_INR = {"chat": Decimal("0.10"), "image": Decimal("4.00")}

_PER_MILLION = Decimal(1_000_000)
_PAISE = Decimal("0.0001")

# A metered call that succeeded is never free. Vendors round their own invoices up to something, and
# a zero-credit ledger line reads as "we were not billed for this" — which would be a lie the margin
# report then repeats.
MIN_METERED_CHARGE = Decimal("0.0001")

# What a turn is assumed to cost before it has happened.
#
# The reservation is a ceiling, not a prediction: it is taken before the model answers, and settled
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

# What a middling turn looks like, for quoting a price before anyone has typed anything.
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
    base_credits: int
    margin_credits: int
    cost_inr: Decimal
    input_rate_inr: Decimal = Decimal(0)   # rupees per million input tokens
    output_rate_inr: Decimal = Decimal(0)  # rupees per million output tokens
    markup: Decimal = Decimal(1)

    @property
    def metered(self) -> bool:
        """True when this slot is billed on real token counts rather than per operation."""
        return self.input_rate_inr > 0 or self.output_rate_inr > 0

    @property
    def credits(self) -> int:
        """What a flat-priced operation charges. Reserved, refunded and displayed as this one
        number. Meaningless for a metered slot, where the charge depends on the answer — use
        `charge_for` there."""
        return self.base_credits + self.margin_credits

    @property
    def revenue_inr(self) -> Decimal:
        """Credits are rupees, so revenue is the charge itself."""
        return Decimal(self.credits)

    @property
    def profit_inr(self) -> Decimal:
        return self.revenue_inr - self.cost_inr

    # ----------------------------------------------------------------- metered

    def vendor_cost_for(self, input_tokens: int, output_tokens: int) -> Decimal:
        """What the vendor bills us for this many tokens, in rupees."""
        billed = (
            Decimal(input_tokens) * self.input_rate_inr
            + Decimal(output_tokens) * self.output_rate_inr
        ) / _PER_MILLION
        return _round(billed)

    def charge_for(self, input_tokens: int, output_tokens: int) -> Decimal:
        """What the customer pays for this many tokens, in credits."""
        return max(
            MIN_METERED_CHARGE,
            _round(self.vendor_cost_for(input_tokens, output_tokens) * self.markup),
        )

    def settle(self, usage: TokenUsage) -> tuple[Decimal, Decimal]:
        """`(credits to charge, what it cost us)` for one completed call.

        A vendor that reported nothing falls back to the flat configured price. Silence is not the
        same as zero tokens, and treating it as zero would hand out free answers whenever a vendor
        changed its response shape — the failure mode should be a slightly wrong bill, never no bill.
        """
        if not self.metered or not usage.reported:
            return Decimal(self.credits), self.cost_inr
        return (
            self.charge_for(usage.input_tokens, usage.output_tokens),
            self.vendor_cost_for(usage.input_tokens, usage.output_tokens),
        )

    def reservation_for(self, prompt_chars: int, has_image: bool = False) -> Decimal:
        """The ceiling held before the model answers, in credits.

        Priced against the largest answer the turn could produce, so a wallet that passed the check
        cannot be overdrawn by the reply that follows. Whatever is not used is returned the instant
        the answer ends.
        """
        if not self.metered:
            return Decimal(self.credits)
        input_tokens = (prompt_chars // CHARS_PER_TOKEN) + (IMAGE_INPUT_TOKENS if has_image else 0)
        return self.charge_for(max(input_tokens, 1), RESERVE_OUTPUT_TOKENS)

    @property
    def typical_credits(self) -> Decimal:
        """A representative price for one operation, for quoting before the fact.

        Flat slots quote exactly what they charge. Metered slots cannot — the price depends on an
        answer nobody has read yet — so they quote a middling turn, which is the honest version of
        a number that used to be presented as exact and never was.
        """
        if not self.metered:
            return Decimal(self.credits)
        return self.charge_for(TYPICAL_INPUT_TOKENS, TYPICAL_OUTPUT_TOKENS)


def from_config(config: ProviderConfig) -> Price:
    return Price(
        provider=config.provider,
        capability=config.capability,
        model=config.model,
        base_credits=config.credit_cost,
        margin_credits=config.margin_credits,
        cost_inr=Decimal(config.provider_cost_inr),
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


async def quote(db: AsyncSession, providers: list[str], capability: str) -> Decimal:
    """What one prompt across these slots is expected to cost the customer, in credits."""
    prices = await load(db, capability)
    return sum(
        ((prices.get(p) or fallback(p, capability)).typical_credits for p in providers),
        Decimal(0),
    )
