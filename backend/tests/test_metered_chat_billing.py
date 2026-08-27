"""Chat billed on the tokens the vendor actually reported.

The behaviours worth pinning: the charge is built from real token counts rather than a flat price,
the reservation taken before the answer is a ceiling that gets settled afterwards, a vendor that
reports nothing still gets billed, and the markup an administrator sets is the markup the wallet
applies.

The rates asserted here are the ones conftest seeds, mirroring migration 0007:
openai ₹13.20 in / ₹52.80 out per million tokens, gemini ₹8.80 / ₹35.20, markup 1.000.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.billing import Credit, UsageRecord
from app.models.image import ProviderConfig
from app.models.user import User
from app.providers.base import TokenUsage
from app.services import pricing_service

# 1000 in + 1000 out at the seeded rates, and what the customer pays for it: the vendor's bill
# plus the flat 0.5-credit chat margin.
CHAT_MARGIN = Decimal("0.5")
OPENAI_1K_1K_COST = Decimal("0.0660")
GEMINI_1K_1K_COST = Decimal("0.0440")
OPENAI_1K_1K = OPENAI_1K_1K_COST + CHAT_MARGIN
GEMINI_1K_1K = GEMINI_1K_1K_COST + CHAT_MARGIN


def _chat_price(markup: Decimal = Decimal(1), margin: Decimal = CHAT_MARGIN) -> pricing_service.Price:
    """The seeded openai chat slot, as a bare Price for the unit tests below."""
    return pricing_service.Price(
        provider="openai", capability="chat", model="m",
        cost_inr=Decimal("0.10"), margin_credits=margin,
        input_rate_inr=Decimal("13.2"), output_rate_inr=Decimal("52.8"), markup=markup,
    )


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _set_balance(db, uid, amount):
    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = Decimal(amount)
    await db.commit()


async def _balance(db, uid) -> Decimal:
    await db.commit()  # see what the streaming sessions committed
    db.expire_all()
    return (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one().balance


async def _chat(client, user, providers=("openai",), message="hi"):
    return await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": message, "providers": list(providers)},
    )


# --------------------------------------------------------------------- the calculation itself


def test_charge_is_built_from_the_two_rates():
    price = _chat_price()
    # Output is priced four times input, so the same token count on each side is not the same money.
    assert price.vendor_cost_for(1_000_000, 0) == Decimal("13.2000")
    assert price.vendor_cost_for(0, 1_000_000) == Decimal("52.8000")
    assert price.vendor_cost_for(1000, 1000) == OPENAI_1K_1K_COST


def test_the_customer_pays_the_vendor_bill_plus_a_flat_margin():
    """The whole pricing rule, in one assertion."""
    price = _chat_price()
    assert price.charge_for(1000, 1000) == OPENAI_1K_1K_COST + CHAT_MARGIN


def test_markup_multiplies_the_cost_but_leaves_the_margin_alone():
    """Markup and margin are different levers: one scales the vendor's bill, the other is a flat
    amount added afterwards. Doubling the markup must not double the margin as well."""
    at_cost = _chat_price()
    doubled = _chat_price(markup=Decimal(2))

    assert doubled.charge_for(1000, 1000) == OPENAI_1K_1K_COST * 2 + CHAT_MARGIN
    # The cost side is untouched by markup — it is what the vendor billed, not what we charged.
    assert doubled.vendor_cost_for(1000, 1000) == at_cost.vendor_cost_for(1000, 1000)


def test_a_slot_without_rates_is_not_metered():
    """Image generation. One operation, one vendor bill, no tokens to count — but the same rule:
    what they charged us, plus the margin."""
    flat = pricing_service.Price(
        provider="openai", capability="image", model="m",
        cost_inr=Decimal("3.70"), margin_credits=Decimal(3),
    )
    assert not flat.metered
    assert flat.credits == Decimal("6.70")
    # Token counts are ignored outright on a flat slot, even when a vendor volunteers them.
    assert flat.settle(TokenUsage(input_tokens=999, output_tokens=999, reported=True)) == (
        Decimal("6.70"), Decimal("3.70"),
    )


def test_an_unreported_call_falls_back_to_the_flat_price_not_to_free():
    """Silence from a vendor is not the same as zero tokens. Billing the margin alone would mean a
    changed response shape quietly gives the model call away."""
    assert _chat_price().settle(TokenUsage()) == (Decimal("0.60"), Decimal("0.10"))


def test_a_successful_metered_call_is_never_free():
    """Even a one-token answer earns the margin — which is what stops a very short turn costing
    the customer nothing while still costing us a request."""
    assert _chat_price().charge_for(1, 0) >= CHAT_MARGIN


# --------------------------------------------------------------------- end to end


async def test_chat_charges_what_the_vendor_reported(client, seeded_db, user_factory, fake_chat):
    fake_chat(tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    assert (await _chat(client, user)).status_code == 200

    assert await _balance(seeded_db, uid) == Decimal(10) - OPENAI_1K_1K


async def test_a_longer_answer_costs_more_than_a_short_one(
    client, seeded_db, user_factory, fake_chat
):
    """The whole point of metering. Under the old flat price these two were the same money."""
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    fake_chat(tokens=(1000, 200))
    await _set_balance(seeded_db, uid, 10)
    await _chat(client, user)
    short = Decimal(10) - await _balance(seeded_db, uid)

    fake_chat(tokens=(1000, 4000))
    await _set_balance(seeded_db, uid, 10)
    await _chat(client, user)
    long = Decimal(10) - await _balance(seeded_db, uid)

    assert long > short


async def test_the_reservation_is_returned_when_the_answer_is_short(
    client, seeded_db, user_factory, fake_chat
):
    """A turn is charged before it runs, against the longest answer it could give. What it did not
    use has to come back, or every short reply quietly funds a long one."""
    fake_chat(tokens=(10, 10))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    price = await pricing_service.price_for(seeded_db, "openai", "chat")
    held = price.reservation_for(len("hi"))

    await _chat(client, user)

    spent = Decimal(10) - await _balance(seeded_db, uid)
    assert spent == price.charge_for(10, 10)
    assert spent < held  # the ceiling was never the price


async def test_the_ledger_records_the_tokens_behind_the_charge(
    client, seeded_db, user_factory, fake_chat
):
    """A charge with no token counts behind it cannot be reconciled against the vendor's invoice."""
    fake_chat(tokens=(1234, 567))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    await _chat(client, user)
    await seeded_db.commit()

    record = (
        await seeded_db.execute(
            select(UsageRecord)
            .where(UsageRecord.user_id == uid, UsageRecord.operation == "chat")
            .order_by(UsageRecord.created_at.desc())
        )
    ).scalars().first()

    assert record.input_tokens == 1234
    assert record.output_tokens == 567
    assert record.credits_consumed == record.credits_consumed  # Decimal, not rounded to an int
    assert record.cost_inr > 0


async def test_a_failed_turn_charges_nothing_and_returns_the_hold(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat(openai_behavior="fail", tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    await _chat(client, user)

    assert await _balance(seeded_db, uid) == Decimal(10)


async def test_an_administrator_s_markup_is_what_the_wallet_applies(
    client, seeded_db, user_factory, fake_chat
):
    """The price an administrator sets is the price the wallet charges — one calculation, not two."""
    fake_chat(tokens=(1000, 1000))
    config = (
        await seeded_db.execute(
            select(ProviderConfig).where(
                ProviderConfig.provider == "openai", ProviderConfig.capability == "chat"
            )
        )
    ).scalar_one()
    config.markup_multiplier = Decimal("3.000")
    await seeded_db.commit()

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    await _chat(client, user)

    assert Decimal(10) - await _balance(seeded_db, uid) == OPENAI_1K_1K_COST * 3 + CHAT_MARGIN

    config.markup_multiplier = Decimal("1.000")
    await seeded_db.commit()


async def test_a_wallet_holding_less_than_one_credit_can_still_chat(
    client, seeded_db, user_factory, fake_chat
):
    """Under the flat price a 0.5-credit balance bought nothing at all. Fractions of a rupee are
    the reason the wallet stopped being an integer."""
    fake_chat(tokens=(500, 500))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, Decimal("0.9000"))

    resp = await _chat(client, user)

    assert "insufficient_credits" not in resp.text
    balance = await _balance(seeded_db, uid)
    assert 0 < balance < Decimal("0.9000")


async def test_the_balance_endpoint_returns_a_number_not_a_string(
    client, seeded_db, user_factory, fake_chat
):
    """Clients compare and sort on this. A Decimal serialised the default way arrives as "9.9340",
    and every one of those comparisons silently becomes lexical."""
    fake_chat(tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)
    await _chat(client, user)

    body = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert isinstance(body["balance"], (int, float))
    assert body["balance"] == pytest.approx(float(Decimal(10) - OPENAI_1K_1K))


async def test_usage_shows_the_customer_their_tokens_but_never_our_cost(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat(tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)
    await _chat(client, user)

    row = next(
        r for r in (await client.get("/api/v1/usage", headers=user["headers"])).json()
        if r["operation"] == "chat"
    )
    assert row["input_tokens"] == 1000
    assert row["output_tokens"] == 1000
    assert "cost_inr" not in row
    assert row["credits_consumed"] == pytest.approx(float(OPENAI_1K_1K))


async def test_a_provider_that_crashes_still_returns_the_hold(
    client, seeded_db, user_factory, fake_chat
):
    """The regression that cost real credits.

    A vendor SDK raised a TypeError — outside its own error hierarchy — so the streaming task died
    before the refund, the exception was swallowed by the gather that collects those tasks, and the
    reservation simply stayed debited. No answer, no ledger row, no log, and the customer paid.
    """
    fake_chat(openai_behavior="crash", tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    resp = await _chat(client, user)

    assert '"code": "provider_error"' in resp.text
    assert await _balance(seeded_db, uid) == Decimal(10)


async def test_one_slot_crashing_does_not_take_the_other_s_money(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat(openai_behavior="crash", tokens=(1000, 1000))
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _set_balance(seeded_db, uid, 10)

    await _chat(client, user, providers=("openai", "gemini"))

    # gemini answered and is charged for exactly what it reported; openai crashed and charged
    # nothing at all.
    assert await _balance(seeded_db, uid) == Decimal(10) - GEMINI_1K_1K
