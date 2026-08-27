import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.billing import Credit, UsageRecord
from app.models.user import User
from app.services.credit_service import (
    InsufficientCreditsError,
    record_usage,
    refund_credits,
    reserve_credits,
)

# The free plan seeded in conftest, and the seeded image price: 5 base + 3 margin.
FREE_CREDITS = 10
IMAGE_CHARGE = Decimal("6.7")  # ₹3.70 vendor bill + 3 margin


async def _user_id(db: AsyncSession, email: str):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def test_reserve_credits_debits_the_one_wallet(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, 10)
    await seeded_db.commit()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.balance == FREE_CREDITS - 10


async def test_reserve_credits_rejects_overdraft(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    with pytest.raises(InsufficientCreditsError):
        await reserve_credits(seeded_db, uid, 999)
    await seeded_db.rollback()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.balance == FREE_CREDITS  # untouched


async def test_balance_never_goes_negative_across_repeated_spends(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 50
    await seeded_db.commit()

    for _ in range(5):
        await reserve_credits(seeded_db, uid, 10)
    await seeded_db.commit()

    with pytest.raises(InsufficientCreditsError):
        await reserve_credits(seeded_db, uid, 1)
    await seeded_db.rollback()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.balance == 0


async def test_concurrent_spends_cannot_double_spend(engine, seeded_db, user_factory):
    """Two overlapping requests must not both succeed against a balance that only covers one.
    The row lock in reserve_credits is what prevents this."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 10
    await seeded_db.commit()

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def spend():
        async with session_factory() as db:
            try:
                await reserve_credits(db, uid, 10)
                await db.commit()
                return "ok"
            except InsufficientCreditsError:
                await db.rollback()
                return "rejected"

    results = await asyncio.gather(spend(), spend())
    assert sorted(results) == ["ok", "rejected"]

    await seeded_db.rollback()
    seeded_db.expire_all()
    final = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert final.balance == 0


async def test_refund_restores_balance(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, 10)
    await refund_credits(seeded_db, uid, 10)
    await seeded_db.commit()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.balance == FREE_CREDITS


async def test_usage_record_captures_both_sides_of_the_margin(seeded_db, user_factory):
    """The ledger has to hold what we were paid *and* what we paid, or the margin report can only
    be reconstructed from today's prices — which would rewrite history every time one changes."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await record_usage(
        seeded_db, user_id=uid, request_id="req-123", provider="openai", model="gpt-image-1",
        operation="image_generate", credits_consumed=IMAGE_CHARGE, cost_inr=Decimal("3.7000"),
        status="success", latency_ms=1500,
    )
    await seeded_db.commit()

    record = (await seeded_db.execute(select(UsageRecord).where(UsageRecord.user_id == uid))).scalar_one()
    assert record.provider == "openai"
    assert record.credits_consumed == IMAGE_CHARGE
    assert record.cost_inr == Decimal("3.7000")
    assert record.status == "success"


async def test_failed_usage_records_no_revenue_and_no_cost(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await record_usage(
        seeded_db, user_id=uid, request_id="req-fail", provider="openai", model="gpt-image-1",
        operation="image_generate", credits_consumed=0, status="failed", error="boom",
    )
    await seeded_db.commit()

    record = (await seeded_db.execute(select(UsageRecord).where(UsageRecord.user_id == uid))).scalar_one()
    assert record.credits_consumed == 0
    assert record.cost_inr == Decimal("0.0000")


async def test_credits_endpoint_reflects_spend(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, 5)
    await seeded_db.commit()

    resp = await client.get("/api/v1/credits", headers=user["headers"])
    assert resp.json() == {"balance": FREE_CREDITS - 5}


async def test_usage_endpoint_returns_own_records(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await record_usage(
        seeded_db, user_id=uid, request_id="r1", provider="gemini", model="m", operation="chat",
        credits_consumed=1, status="success",
    )
    await seeded_db.commit()

    resp = await client.get("/api/v1/usage", headers=user["headers"])
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["provider"] == "gemini"


async def test_usage_response_hides_what_the_operation_cost_us(client, seeded_db, user_factory):
    """`cost_inr` is our supplier bill. Publishing it would hand every customer the exact margin."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await record_usage(
        seeded_db, user_id=uid, request_id="r1", provider="openai", model="gpt-image-1",
        operation="image_generate", credits_consumed=IMAGE_CHARGE, cost_inr=Decimal("3.7000"),
        status="success",
    )
    await seeded_db.commit()

    body = (await client.get("/api/v1/usage", headers=user["headers"])).json()
    assert "cost_inr" not in body[0]
    assert body[0]["credits_consumed"] == float(IMAGE_CHARGE)


async def test_image_generation_rejected_without_enough_credits(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = IMAGE_CHARGE - 1
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "a cat", "providers": ["openai"]}
    )
    assert resp.status_code == 402
