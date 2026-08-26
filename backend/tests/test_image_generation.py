"""Covers the parallel multi-provider generation flow, including partial failure — the case the
product depends on: if one provider fails, the other's result must still be delivered."""
import asyncio
import io
import time
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.image import GeneratedImage, GenerationRequest, GenerationResult
from app.models.user import User
from app.providers.base import ImageResult, ProviderError
from app.services import image_orchestrator, image_service


def _png_bytes(size=(64, 64), color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


class _FakeProvider:
    def __init__(self, name, behavior):
        self.name = name
        self._behavior = behavior
        self.calls = 0
        # When this provider was inside generate_image, so a test can ask whether two of them were
        # ever in flight at the same moment.
        self.started_at: float | None = None
        self.finished_at: float | None = None

    async def generate_image(self, prompt, model, input_image=None, input_mime=None, aspect="portrait"):
        self.calls += 1
        self.started_at = time.perf_counter()
        try:
            if self._behavior == "fail":
                raise ProviderError(self.name, "simulated provider outage", retryable=False)
            if self._behavior == "slow":
                await asyncio.sleep(0.2)
            return ImageResult(image_bytes=_png_bytes(), content_type="image/png")
        finally:
            self.finished_at = time.perf_counter()


@pytest.fixture
def fake_providers(monkeypatch):
    registry: dict[str, _FakeProvider] = {}

    def _install(openai_behavior="ok", gemini_behavior="ok"):
        registry["openai"] = _FakeProvider("openai", openai_behavior)
        registry["gemini"] = _FakeProvider("gemini", gemini_behavior)
        monkeypatch.setattr(image_service, "get_image_provider", lambda name: registry[name])
        return registry

    return _install


async def _top_up(db, uid, amount=100):
    from app.models.billing import Credit

    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = amount
    await db.commit()


async def test_generate_creates_pending_results_for_each_provider(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))

    resp = await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={"prompt": "a cinematic portrait", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert {r["provider"] for r in body["results"]} == {"openai", "gemini"}
    assert all(r["status"] == "pending" for r in body["results"])


async def test_generate_debits_credits_for_each_provider(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]), amount=100)

    await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["balance"] == 100 - 16  # 8 per provider (5 base + 3 margin), both up front


async def test_partial_reservation_is_rolled_back_when_second_provider_unaffordable(
    client, seeded_db, user_factory, monkeypatch
):
    """The free plan's 50 credits do not cover two slots plus what the account already spent, and
    a refusal must leave the wallet exactly as it found it — not half-charged."""
    user = await user_factory()

    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid, amount=15)  # covers one slot at 8, not two at 16

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 402

    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["balance"] == 15


async def test_both_providers_run_and_persist_images(client, seeded_db, user_factory, monkeypatch, fake_providers):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    fake_providers("ok", "ok")

    # Give enough credits for two providers.
    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "a red square", "providers": ["openai", "gemini"]},
    )
    request_id = uuid.UUID(resp.json()["id"])

    await image_orchestrator.run_generation(request_id)

    seeded_db.expire_all()
    results = (
        await seeded_db.execute(select(GenerationResult).where(GenerationResult.request_id == request_id))
    ).scalars().all()
    assert len(results) == 2
    assert all(r.status == "completed" for r in results)
    assert all(r.generated_image_id is not None for r in results)

    images = (await seeded_db.execute(select(GeneratedImage).where(GeneratedImage.user_id == uid))).scalars().all()
    assert len(images) == 2
    assert all(img.thumbnail_filename for img in images)


async def test_one_provider_failing_still_delivers_the_other(
    client, seeded_db, user_factory, monkeypatch, fake_providers
):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    fake_providers(openai_behavior="ok", gemini_behavior="fail")

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "a red square", "providers": ["openai", "gemini"]},
    )
    request_id = uuid.UUID(resp.json()["id"])
    await image_orchestrator.run_generation(request_id)

    seeded_db.expire_all()
    results = {
        r.provider: r
        for r in (
            await seeded_db.execute(select(GenerationResult).where(GenerationResult.request_id == request_id))
        ).scalars().all()
    }
    assert results["openai"].status == "completed"
    assert results["openai"].generated_image_id is not None
    assert results["gemini"].status == "failed"
    assert results["gemini"].error  # user-facing, generic
    assert "simulated provider outage" not in results["gemini"].error

    gen_request = (
        await seeded_db.execute(select(GenerationRequest).where(GenerationRequest.id == request_id))
    ).scalar_one()
    assert gen_request.status == "partial"

    # And the API surfaces the successful one.
    detail = await client.get(f"/api/v1/images/{request_id}", headers=user["headers"])
    by_provider = {r["provider"]: r for r in detail.json()["results"]}
    assert by_provider["openai"]["image_url"] is not None
    assert by_provider["gemini"]["image_url"] is None


async def test_failed_provider_credits_are_refunded(client, seeded_db, user_factory, monkeypatch, fake_providers):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    fake_providers(openai_behavior="fail", gemini_behavior="fail")

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(resp.json()["id"]))

    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["balance"] == 100  # both reserved then both refunded


async def test_providers_run_concurrently_not_sequentially(
    client, seeded_db, user_factory, fake_providers
):
    """One slot must never wait for the other.

    Asserted as an overlap rather than as a stopwatch on the whole call. A total-elapsed budget was
    really measuring "generation plus everything around it", so it broke the moment prompt
    composition added a few database round-trips before the fan-out — and it would have gone on
    breaking on any machine with a slower database. Whether two coroutines were in flight together
    is a fact about the code; how long the surrounding work takes is a fact about the hardware.
    """
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    providers = fake_providers(openai_behavior="slow", gemini_behavior="slow")

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(resp.json()["id"]))

    openai, gemini = providers["openai"], providers["gemini"]
    assert openai.calls == 1 and gemini.calls == 1, "both slots must have been asked"
    assert None not in (openai.started_at, openai.finished_at, gemini.started_at, gemini.finished_at)

    # There was a moment when neither had finished and both had begun. Run sequentially, the second
    # provider's start would fall after the first one's finish and this would not hold.
    latest_start = max(openai.started_at, gemini.started_at)
    earliest_finish = min(openai.finished_at, gemini.finished_at)
    assert latest_start < earliest_finish, (
        "providers ran one after the other: "
        f"openai {openai.started_at:.3f}-{openai.finished_at:.3f}, "
        f"gemini {gemini.started_at:.3f}-{gemini.finished_at:.3f}"
    )


async def test_regenerate_creates_new_result_linked_to_parent(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    # Two generations, and the free grant covers one — a retry is billed like any other picture.
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "x", "providers": ["openai"]}
    )
    request_id = resp.json()["id"]

    again = await client.post(
        f"/api/v1/images/{request_id}/regenerate", headers=user["headers"], json={"provider": "openai"}
    )
    assert again.status_code == 202
    assert len(again.json()["results"]) == 2

    seeded_db.expire_all()
    results = (
        await seeded_db.execute(
            select(GenerationResult).where(GenerationResult.request_id == uuid.UUID(request_id))
        )
    ).scalars().all()
    assert any(r.parent_result_id is not None for r in results)


async def test_generate_rejects_unknown_provider(client, user_factory):
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "x", "providers": ["not-a-provider"]}
    )
    assert resp.status_code == 400


async def test_generate_rejects_empty_prompt(client, user_factory):
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "", "providers": ["openai"]}
    )
    assert resp.status_code == 422


async def test_generate_requires_authentication(client):
    resp = await client.post("/api/v1/images/generate", json={"prompt": "x", "providers": ["openai"]})
    assert resp.status_code == 401
