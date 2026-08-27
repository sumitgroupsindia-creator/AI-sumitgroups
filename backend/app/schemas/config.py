from decimal import Decimal

from pydantic import BaseModel, field_serializer


class PublicModelSlot(BaseModel):
    """A model slot as customers see it.

    Carries the product's own naming rather than the provider's: which vendor sits behind a slot is
    an implementation detail that can change without the UI changing. `provider` is present only
    because the client has to name the slot back to us when submitting a generation.
    """

    provider: str
    slot: str
    tier: str
    description: str
    chat_enabled: bool
    image_enabled: bool
    # Free accounts cannot select this slot. Published so the composer can show it locked with a
    # route to the pricing page, rather than letting someone pick it and meet a 402.
    requires_paid_plan: bool = False
    # What one operation on this slot costs the customer, margin included. One credit is one rupee.
    #
    # Chat is metered, so its figure is what a middling turn comes to rather than a fixed price —
    # a long answer costs more and a one-liner costs less. Quoting it as though it were exact is
    # what the old flat number did, and it was wrong in both directions.
    chat_credit_cost: Decimal
    image_credit_cost: Decimal

    @field_serializer("chat_credit_cost", "image_credit_cost")
    def _as_number(self, value: Decimal) -> float:
        return float(value)
