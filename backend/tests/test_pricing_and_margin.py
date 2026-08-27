"""The product's economics: one rupee-denominated wallet, a vendor cost we record, and the margin
between them.

The numbers asserted here are the ones conftest seeds, which mirror the 0005 migration — chat at
1 credit with no markup, images at 5 base + 3 margin = 8 credits against a ~₹3.70 vendor bill.
"""
import asyncio
import io
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.models.billing import Credit
from app.models.image import ProviderConfig
from app.models.user import User
from app.providers.base import ImageResult, ProviderError
from app.services import image_orchestrator, image_service

IMAGE_CHARGE = Decimal("6.7")  # ₹3.70 vendor bill + 3 margin
OPENAI_IMAGE_COST = Decimal("3.7000")
OPENAI_CHAT_COST = Decimal("0.1000")  # what one router or photo-reading call costs us


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


class _FakeProvider:
    def __init__(self, behavior="ok"):
        self._behavior = behavior

    async def generate_image(self, prompt, model, input_image=None, input_mime=None, aspect="portrait"):
        if self._behavior == "fail":
            raise ProviderError("fake", "simulated outage", retryable=False)
        return ImageResult(image_bytes=_png_bytes(), content_type="image/png")


@pytest_asyncio.fixture(autouse=True)
async def restore_prices(seeded_db):
    """The schema is built once for the whole session, so provider prices survive between tests.
    Anything a test repriced is put back, or the next test is asserting against someone else's
    numbers — which is exactly how the first draft of this file failed."""
    columns = (
        "provider_cost_inr", "margin_credits",
        "input_cost_per_mtok_inr", "output_cost_per_mtok_inr", "markup_multiplier",
    )
    before = {
        row.id: {column: getattr(row, column) for column in columns}
        for row in (await seeded_db.execute(select(ProviderConfig))).scalars().all()
    }
    yield
    seeded_db.expire_all()
    for row in (await seeded_db.execute(select(ProviderConfig))).scalars().all():
        for column, value in before.get(row.id, {}).items():
            setattr(row, column, value)
    await seeded_db.commit()


async def _pricing(client, headers) -> dict:
    return (await client.get("/api/v1/admin/pricing?days=30", headers=headers)).json()


@pytest.fixture
def fake_image_providers(monkeypatch):
    def _install(behavior="ok"):
        monkeypatch.setattr(image_service, "get_image_provider", lambda name: _FakeProvider(behavior))

    return _install


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _set_balance(db, uid, amount):
    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = amount
    await db.commit()


async def _admin_headers(client, seeded_db, user_factory):
    user = await user_factory()
    db_user = (await seeded_db.execute(select(User).where(User.email == user["email"]))).scalar_one()
    db_user.is_admin = True
    await seeded_db.commit()
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    return {"Authorization": f"Bearer {tokens.json()['access_token']}"}


# --------------------------------------------------------------------------- charging


async def test_image_charges_base_plus_margin(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)

    await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )

    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    assert balance == pytest.approx(float(Decimal(100) - IMAGE_CHARGE))


async def test_margin_is_charged_per_picture_not_per_prompt(client, seeded_db, user_factory, monkeypatch):
    """Two slots means two vendor bills, so it has to mean two margins."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)

    await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )

    # Two slots, two vendor bills, two margins — and the bills differ, so this is not simply
    # twice one slot: openai ₹3.70 + 3, gemini ₹3.50 + 3.
    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    assert balance == pytest.approx(float(Decimal(100) - IMAGE_CHARGE - Decimal("6.5")))


async def test_chat_and_images_draw_on_the_same_wallet(client, seeded_db, user_factory, monkeypatch):
    """The point of a rupee-denominated credit: a picture and a paragraph spend the same money."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, IMAGE_CHARGE)

    await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )

    # The image consumed everything, so there is nothing left for a chat turn either.
    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["openai"]},
    )
    assert "insufficient_credits" in resp.text


async def test_failure_refunds_the_margin_too(
    client, seeded_db, user_factory, monkeypatch, fake_image_providers
):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)
    fake_image_providers("fail")

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    assert balance == 100  # the whole charge came back, margin included


# --------------------------------------------------------------------------- regeneration


async def test_regenerate_charges_again(client, seeded_db, user_factory, monkeypatch):
    """A retry bills the vendor again, so it must bill the customer again. It used to be free."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    generation_id = created.json()["id"]

    resp = await client.post(
        f"/api/v1/images/{generation_id}/regenerate", headers=user["headers"], json={"provider": "openai"}
    )
    assert resp.status_code == 202

    # Two slots, two vendor bills, two margins — and the bills differ, so this is not simply
    # twice one slot: openai ₹3.70 + 3, gemini ₹3.50 + 3.
    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    # Both charges are openai's, so this one really is twice the same slot.
    assert balance == pytest.approx(float(Decimal(100) - 2 * IMAGE_CHARGE))


async def test_regenerate_is_refused_when_the_wallet_is_empty(
    client, seeded_db, user_factory, monkeypatch
):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, IMAGE_CHARGE)

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    resp = await client.post(
        f"/api/v1/images/{created.json()['id']}/regenerate", headers=user["headers"], json={}
    )
    assert resp.status_code == 402


async def test_failed_regeneration_cannot_mint_credits(
    client, seeded_db, user_factory, monkeypatch, fake_image_providers
):
    """The refund path runs against whatever the retry reserved. If the retry reserved nothing, the
    refund would create credits out of thin air — this is the regression that guards it."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)
    fake_image_providers("fail")

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    generation_id = uuid.UUID(created.json()["id"])
    await image_orchestrator.run_generation(generation_id)

    await client.post(
        f"/api/v1/images/{generation_id}/regenerate", headers=user["headers"], json={"provider": "openai"}
    )
    await image_orchestrator.run_generation(generation_id)

    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    assert balance == 100  # two charges, two refunds — never more than we started with


# --------------------------------------------------------------------------- admin surface


async def test_admin_models_expose_cost_charge_and_profit(client, seeded_db, user_factory):
    headers = await _admin_headers(client, seeded_db, user_factory)

    rows = (await client.get("/api/v1/admin/models", headers=headers)).json()
    image_row = next(r for r in rows if r["provider"] == "openai" and r["capability"] == "image")

    assert Decimal(image_row["provider_cost_inr"]) == OPENAI_IMAGE_COST
    assert Decimal(image_row["margin_credits"]) == 3
    # The charge is the vendor's bill plus the margin, so the profit *is* the margin.
    assert image_row["charge_credits"] == float(IMAGE_CHARGE)
    assert Decimal(image_row["profit_inr"]) == Decimal(3)


async def test_admin_can_change_the_margin_and_the_wallet_follows(
    client, seeded_db, user_factory, monkeypatch
):
    """The price an administrator sets is the price the wallet charges — one calculation, not two."""
    headers = await _admin_headers(client, seeded_db, user_factory)
    rows = (await client.get("/api/v1/admin/models", headers=headers)).json()
    image_row = next(r for r in rows if r["provider"] == "openai" and r["capability"] == "image")

    updated = await client.patch(
        f"/api/v1/admin/models/{image_row['id']}", headers=headers, json={"margin_credits": 10}
    )
    assert updated.json()["charge_credits"] == float(OPENAI_IMAGE_COST + 10)

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)

    await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    balance = (await client.get("/api/v1/credits", headers=user["headers"])).json()["balance"]
    assert balance == pytest.approx(float(Decimal(100) - (OPENAI_IMAGE_COST + 10)))


async def test_public_slots_quote_the_full_charge_including_margin(client, seeded_db):
    """What the composer shows must be what the wallet takes, or the price on screen is a lie.

    Exactly so for a picture, which has one price. Chat is metered, so the quote is a representative
    turn rather than a promise — but it still has to be in the right region, and the old flat "1
    credit" was roughly thirty times over.
    """
    slots = (await client.get("/api/v1/config/models")).json()
    openai_slot = next(s for s in slots if s["provider"] == "openai")

    assert openai_slot["image_credit_cost"] == float(IMAGE_CHARGE)
    # 700 in + 400 out at the seeded rates costs ₹0.0304; the customer pays that plus the
    # 0.5-credit margin.
    assert openai_slot["chat_credit_cost"] == pytest.approx(0.5304)


async def test_pricing_report_totals_revenue_cost_and_profit(
    client, seeded_db, user_factory, monkeypatch, fake_image_providers
):
    headers = await _admin_headers(client, seeded_db, user_factory)
    before = await _pricing(client, headers)

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)
    fake_image_providers("ok")

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    after = await _pricing(client, headers)

    # One picture sold. The router that chose its style ran too, and cost us a chat call — so spend
    # is the picture plus that call, while the operation count stays at the one thing we sold.
    assert after["total_operations"] - before["total_operations"] == 1
    assert Decimal(after["total_revenue_inr"]) - Decimal(before["total_revenue_inr"]) == IMAGE_CHARGE
    spend = Decimal(after["total_spend_inr"]) - Decimal(before["total_spend_inr"])
    assert spend == OPENAI_IMAGE_COST + OPENAI_CHAT_COST
    assert Decimal(after["total_profit_inr"]) - Decimal(before["total_profit_inr"]) == (
        IMAGE_CHARGE - spend
    )

    row = next(r for r in after["rows"] if r["provider"] == "openai" and r["capability"] == "image")
    assert row["charge_credits"] == float(IMAGE_CHARGE)


async def test_pricing_report_excludes_refunded_failures(
    client, seeded_db, user_factory, monkeypatch, fake_image_providers
):
    """A failure was refunded, so it earned nothing — counting it would invent revenue."""
    headers = await _admin_headers(client, seeded_db, user_factory)
    before = await _pricing(client, headers)

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 100)
    fake_image_providers("fail")

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    after = await _pricing(client, headers)
    assert after["total_operations"] == before["total_operations"]
    assert Decimal(after["total_revenue_inr"]) == Decimal(before["total_revenue_inr"])


async def test_a_provider_without_a_config_row_is_not_free(seeded_db):
    """A missing price must make an operation expensive, never free."""
    from app.services import pricing_service

    await seeded_db.execute(
        ProviderConfig.__table__.delete().where(
            ProviderConfig.provider == "openai", ProviderConfig.capability == "image"
        )
    )
    await seeded_db.commit()

    price = await pricing_service.price_for(seeded_db, "openai", "image")
    assert price.credits > 0
    assert price.margin_credits > 0
