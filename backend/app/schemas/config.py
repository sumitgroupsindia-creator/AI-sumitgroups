from pydantic import BaseModel


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
    chat_credit_cost: int
    image_credit_cost: int
