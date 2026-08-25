import hashlib
import hmac
from functools import lru_cache

import razorpay

from app.core.config import get_settings
from app.services import settings_service
from app.services.payment.base import CheckoutOrder, PaymentProvider, WebhookEvent

settings = get_settings()


@lru_cache(maxsize=4)
def _client_for(key_id: str, key_secret: str) -> razorpay.Client:
    """One client per distinct credential pair, so keys rotated in the admin UI apply immediately."""
    return razorpay.Client(auth=(key_id, key_secret))


class RazorpayProvider(PaymentProvider):
    name = "razorpay"

    @property
    def _client(self) -> razorpay.Client:
        return _client_for(
            settings_service.get_str_sync("razorpay_key_id"),
            settings_service.get_str_sync("razorpay_key_secret"),
        )

    async def create_order(self, amount_minor_units: int, currency: str, receipt: str) -> CheckoutOrder:
        order = self._client.order.create(
            {"amount": amount_minor_units, "currency": currency, "receipt": receipt, "payment_capture": 1}
        )
        return CheckoutOrder(
            order_id=order["id"],
            amount_minor_units=amount_minor_units,
            currency=currency,
            key_id=settings_service.get_str_sync("razorpay_key_id"),
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        secret = settings_service.get_str_sync("razorpay_webhook_secret")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        event_type = payload.get("event", "")
        entity = (payload.get("payload", {}).get("subscription") or payload.get("payload", {}).get("payment") or {})
        entity = entity.get("entity", entity)
        return WebhookEvent(
            event_type=event_type,
            provider_subscription_id=entity.get("id") if "subscription" in event_type else None,
            provider_payment_id=entity.get("id") if "payment" in event_type else None,
            raw_payload=payload,
        )

    async def cancel_subscription(self, provider_subscription_id: str) -> None:
        self._client.subscription.cancel(provider_subscription_id)


@lru_cache
def get_payment_provider() -> PaymentProvider:
    if settings.payment_provider == "razorpay":
        return RazorpayProvider()
    raise ValueError(f"Unsupported payment provider: {settings.payment_provider}")
