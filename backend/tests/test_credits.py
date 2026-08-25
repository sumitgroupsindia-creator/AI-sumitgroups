import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.billing import Credit, UsageRecord
from app.models.user import User
from app.services.credit_service import (
    InsufficientCreditsError,
    get_or_create_credits,
    record_usage,
    refund_credits,
    reserve_credits,
)


async def _user_id(db: AsyncSession, email: str):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def test_reserve_credits_debits_balance(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, "image", 10)
    await seeded_db.commit()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.image_balance == 0
    assert credit.chat_balance == 50


async def test_reserve_credits_rejects_overdraft(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    with pytest.raises(InsufficientCreditsError):
        await reserve_credits(seeded_db, uid, "image", 999)
    await seeded_db.rollback()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.image_balance == 10  # untouched


async def test_balance_never_goes_negative_across_repeated_spends(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    for _ in range(5):
        await reserve_credits(seeded_db, uid, "chat", 10)
    await seeded_db.commit()

    with pytest.raises(InsufficientCreditsError):
        await reserve_credits(seeded_db, uid, "chat", 1)
    await seeded_db.rollback()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.chat_balance == 0


async def test_concurrent_spends_cannot_double_spend(engine, seeded_db, user_factory):
    """Two overlapping requests must not both succeed against a balance that only covers one.
    The row lock in reserve_credits is what prevents this."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 10
    await seeded_db.commit()

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def spend():
        async with session_factory() as db:
            try:
                await reserve_credits(db, uid, "image", 10)
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
    assert final.image_balance == 0


async def test_refund_restores_balance(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, "image", 10)
    await refund_credits(seeded_db, uid, "image", 10)
    await seeded_db.commit()

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    assert credit.image_balance == 10


async def test_usage_record_written(seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await record_usage(
        seeded_db, user_id=uid, request_id="req-123", provider="openai", model="gpt-image-1",
        operation="image_generate", credits_consumed=10, status="success", latency_ms=1500,
    )
    await seeded_db.commit()

    record = (await seeded_db.execute(select(UsageRecord).where(UsageRecord.user_id == uid))).scalar_one()
    assert record.provider == "openai"
    assert record.credits_consumed == 10
    assert record.status == "success"


async def test_credits_endpoint_reflects_spend(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    await reserve_credits(seeded_db, uid, "chat", 5)
    await seeded_db.commit()

    resp = await client.get("/api/v1/credits", headers=user["headers"])
    assert resp.json() == {"chat_balance": 45, "image_balance": 10}


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


async def test_image_generation_rejected_without_enough_credits(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 5  # one provider costs 10
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "a cat", "providers": ["openai"]}
    )
    assert resp.status_code == 402
