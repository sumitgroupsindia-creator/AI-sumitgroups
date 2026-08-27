"""A free account cannot reach the premium slot, and therefore cannot ask both slots at once.

Enforced on the server, not just in the composer: `providers` is a field in a request body, so a
gate that lived only in the browser would be a suggestion. These tests call the API the way an
edited request would.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.billing import Credit, Plan, Subscription
from app.models.settings import ProviderBrand
from app.models.user import User
from app.services import entitlement_service


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _fund(db, uid, amount=100):
    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = Decimal(amount)
    await db.commit()


async def _subscribe(db, uid, code: str, status: str = "active"):
    plan = (await db.execute(select(Plan).where(Plan.code == code))).scalar_one()
    db.add(Subscription(user_id=uid, plan_id=plan.id, status=status, provider="razorpay"))
    await db.commit()


# --------------------------------------------------------------------------- the rule


async def test_a_free_account_may_use_the_standard_slot(client, seeded_db, user_factory, fake_chat):
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    await _fund(seeded_db, await _user_id(seeded_db, user["email"]))

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["openai"]},
    )
    assert resp.status_code == 200


async def test_a_free_account_is_refused_the_premium_slot(client, seeded_db, user_factory, fake_chat):
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    await _fund(seeded_db, await _user_id(seeded_db, user["email"]))

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["gemini"]},
    )
    assert resp.status_code == 402


async def test_a_free_account_cannot_ask_both_slots(client, seeded_db, user_factory, fake_chat):
    """Not a separate rule — "both" contains the premium slot, so the same check catches it."""
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    await _fund(seeded_db, await _user_id(seeded_db, user["email"]))

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 402


async def test_the_refusal_costs_nothing(client, seeded_db, user_factory, fake_chat):
    """Refused before anything is reserved, so a blocked attempt cannot quietly spend credits."""
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid, 50)

    await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["openai", "gemini"]},
    )

    seeded_db.expire_all()
    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.balance == Decimal(50)


async def test_a_paid_account_may_use_the_premium_slot(client, seeded_db, user_factory, fake_chat):
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid)
    await _subscribe(seeded_db, uid, "pro")

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 200


async def test_a_subscription_that_is_not_active_does_not_unlock_it(
    client, seeded_db, user_factory, fake_chat
):
    """Started checkout is not the same as paid. A pending row must not buy anything."""
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid)
    await _subscribe(seeded_db, uid, "pro", status="pending")

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"],
        json={"message": "hi", "providers": ["gemini"]},
    )
    assert resp.status_code == 402


async def test_a_zero_priced_plan_does_not_unlock_it(client, seeded_db, user_factory, fake_chat):
    """Entitlement follows the price, not the plan's name — otherwise a second free tier, or a
    renamed one, would quietly hand out the premium slot."""
    fake_chat(tokens=(100, 100))
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid)
    await _subscribe(seeded_db, uid, "free")

    assert await entitlement_service.has_paid_plan(seeded_db, uid) is False


# --------------------------------------------------------------------------- images


async def test_image_generation_is_gated_the_same_way(client, seeded_db, user_factory):
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid)

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 402


async def test_regeneration_cannot_be_used_to_reach_a_locked_slot(
    client, seeded_db, user_factory
):
    """The obvious way around a gate on `generate` is to create a permitted request and then
    regenerate it against the locked slot."""
    user = await user_factory(plan="free")
    uid = await _user_id(seeded_db, user["email"])
    await _fund(seeded_db, uid)

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"]},
    )
    assert created.status_code == 202

    resp = await client.post(
        f"/api/v1/images/{created.json()['id']}/regenerate",
        headers=user["headers"], json={"provider": "gemini"},
    )
    assert resp.status_code == 402


# --------------------------------------------------------------------------- the UI's copy


async def test_public_slots_say_which_one_needs_paying_for(client, seeded_db):
    """So the composer can show it locked rather than letting someone pick it and meet a 402."""
    slots = (await client.get("/api/v1/config/models")).json()
    by_provider = {s["provider"]: s for s in slots}

    assert by_provider["openai"]["requires_paid_plan"] is False
    assert by_provider["gemini"]["requires_paid_plan"] is True


async def test_an_administrator_can_move_which_slot_is_premium(seeded_db):
    """The gate reads from the brand row, so this is a setting rather than a deploy."""
    brand = (
        await seeded_db.execute(select(ProviderBrand).where(ProviderBrand.provider == "gemini"))
    ).scalar_one()
    brand.requires_paid_plan = False
    await seeded_db.commit()

    assert await entitlement_service.paid_only_providers(seeded_db) == set()

    brand.requires_paid_plan = True
    await seeded_db.commit()
