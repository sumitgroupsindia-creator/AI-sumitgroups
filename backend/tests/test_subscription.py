import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.models.billing import Credit, Plan, Subscription
from app.models.user import User
from app.services import subscription_service
from app.services.payment.base import CheckoutOrder, PaymentProvider, WebhookEvent
from app.services.payment.razorpay_provider import RazorpayProvider, get_payment_provider


WEBHOOK_SECRET = "test_webhook_secret"


class FakePaymentProvider(PaymentProvider):
    name = "razorpay"

    def __init__(self):
        self.cancelled: list[str] = []

    async def create_order(self, amount_minor_units, currency, receipt):
        return CheckoutOrder(
            order_id=f"order_{receipt[:8]}", amount_minor_units=amount_minor_units,
            currency=currency, key_id="rzp_test_key",
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
        return WebhookEvent(
            event_type=payload.get("event", ""),
            provider_subscription_id=entity.get("id"),
            provider_payment_id=None,
            raw_payload=payload,
        )

    async def cancel_subscription(self, provider_subscription_id: str) -> None:
        self.cancelled.append(provider_subscription_id)


@pytest.fixture
def fake_payment(client):
    from app.main import app

    provider = FakePaymentProvider()
    app.dependency_overrides[get_payment_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_payment_provider, None)


def _sign(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


# ---------- plans ----------


async def test_plans_are_database_driven_and_public(client):
    resp = await client.get("/api/v1/subscription/plans")
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert {"free", "pro"} <= codes
    for plan in resp.json():
        # Limits must come from the database so the frontend never hard-codes them.
        assert "monthly_chat_credits" in plan and "monthly_image_credits" in plan


async def test_new_user_starts_on_free_plan(client, user_factory):
    user = await user_factory()
    resp = await client.get("/api/v1/subscription", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["plan"]["code"] == "free"


# ---------- checkout ----------


async def test_checkout_creates_pending_subscription_and_order(client, seeded_db, user_factory, fake_payment):
    user = await user_factory()
    resp = await client.post("/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "pro"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"].startswith("order_")
    assert body["amount"] == 99900  # 999.00 INR in paise
    assert body["currency"] == "INR"
    assert body["key_id"] == "rzp_test_key"

    seeded_db.expire_all()
    uid = await _user_id(seeded_db, user["email"])
    subs = (await seeded_db.execute(select(Subscription).where(Subscription.user_id == uid))).scalars().all()
    pending = [s for s in subs if s.status == "pending"]
    assert len(pending) == 1
    assert pending[0].provider_subscription_id == body["order_id"]


async def test_checkout_rejects_free_plan(client, user_factory, fake_payment):
    user = await user_factory()
    resp = await client.post("/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "free"})
    assert resp.status_code == 400


async def test_checkout_rejects_unknown_plan(client, user_factory, fake_payment):
    user = await user_factory()
    resp = await client.post("/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "nope"})
    assert resp.status_code == 400


async def test_checkout_requires_authentication(client, fake_payment):
    resp = await client.post("/api/v1/subscription/checkout", json={"plan_code": "pro"})
    assert resp.status_code == 401


# ---------- webhook ----------


async def test_webhook_rejects_missing_signature(client, fake_payment):
    resp = await client.post("/api/v1/subscription/webhook", json={"event": "subscription.activated"})
    assert resp.status_code == 400


async def test_webhook_rejects_forged_signature(client, fake_payment):
    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {"id": "order_x"}}}}
    raw = json.dumps(body).encode()
    resp = await client.post(
        "/api/v1/subscription/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


async def test_valid_webhook_activates_subscription_and_grants_credits(
    client, seeded_db, user_factory, fake_payment
):
    user = await user_factory()
    checkout = await client.post(
        "/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "pro"}
    )
    order_id = checkout.json()["order_id"]

    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {"id": order_id}}}}
    raw, signature = _sign(body)
    resp = await client.post(
        "/api/v1/subscription/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    seeded_db.expire_all()
    uid = await _user_id(seeded_db, user["email"])
    sub = (
        await seeded_db.execute(
            select(Subscription).where(Subscription.provider_subscription_id == order_id)
        )
    ).scalar_one()
    assert sub.status == "active"
    assert sub.current_period_end is not None

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.chat_balance == 1000  # pro plan allowance
    assert credit.image_balance == 200


async def test_webhook_for_unknown_subscription_is_ignored_not_crashed(client, fake_payment):
    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {"id": "order_unknown"}}}}
    raw, signature = _sign(body)
    resp = await client.post(
        "/api/v1/subscription/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200


async def test_cancellation_webhook_expires_subscription(client, seeded_db, user_factory, fake_payment):
    user = await user_factory()
    checkout = await client.post(
        "/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "pro"}
    )
    order_id = checkout.json()["order_id"]

    for event in ("subscription.activated", "subscription.cancelled"):
        body = {"event": event, "payload": {"subscription": {"entity": {"id": order_id}}}}
        raw, signature = _sign(body)
        await client.post(
            "/api/v1/subscription/webhook",
            content=raw,
            headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
        )

    seeded_db.expire_all()
    sub = (
        await seeded_db.execute(
            select(Subscription).where(Subscription.provider_subscription_id == order_id)
        )
    ).scalar_one()
    assert sub.status == "expired"


async def test_cancel_endpoint_marks_cancel_at_period_end(client, seeded_db, user_factory, fake_payment):
    user = await user_factory()
    checkout = await client.post(
        "/api/v1/subscription/checkout", headers=user["headers"], json={"plan_code": "pro"}
    )
    order_id = checkout.json()["order_id"]
    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {"id": order_id}}}}
    raw, signature = _sign(body)
    await client.post(
        "/api/v1/subscription/webhook",
        content=raw,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )

    resp = await client.post("/api/v1/subscription/cancel", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["cancel_at_period_end"] is True
    assert order_id in fake_payment.cancelled


def test_razorpay_signature_verification_is_constant_time_hmac(monkeypatch):
    """The real provider must verify with HMAC-SHA256 over the raw body, not trust the header."""
    from app.services.payment import razorpay_provider

    monkeypatch.setattr(razorpay_provider.settings, "razorpay_webhook_secret", "s3cret")
    monkeypatch.setattr(razorpay_provider.settings, "razorpay_key_id", "k")
    monkeypatch.setattr(razorpay_provider.settings, "razorpay_key_secret", "k")
    provider = RazorpayProvider()

    payload = b'{"event":"payment.captured"}'
    good = hmac.new(b"s3cret", payload, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(payload, good) is True
    assert provider.verify_webhook_signature(payload, "0" * 64) is False
    assert provider.verify_webhook_signature(b'{"event":"tampered"}', good) is False
