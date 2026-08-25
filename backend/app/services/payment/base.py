from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CheckoutOrder:
    order_id: str
    amount_minor_units: int
    currency: str
    key_id: str


@dataclass
class WebhookEvent:
    event_type: str  # subscription.activated | payment.captured | subscription.cancelled | ...
    provider_subscription_id: str | None
    provider_payment_id: str | None
    raw_payload: dict


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    async def create_order(self, amount_minor_units: int, currency: str, receipt: str) -> CheckoutOrder: ...

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> WebhookEvent: ...

    @abstractmethod
    async def cancel_subscription(self, provider_subscription_id: str) -> None: ...
