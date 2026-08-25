"""Covers the parallel multi-provider generation flow, including partial failure — the case the
product depends on: if one provider fails, the other's result must still be delivered."""
import asyncio
import io
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

    async def generate_image(self, prompt, model, input_image=None, input_mime=None):
        self.calls += 1
        if self._behavior == "fail":
            raise ProviderError(self.name, "simulated provider outage", retryable=False)
        if self._behavior == "slow":
            await asyncio.sleep(0.2)
        return ImageResult(image_bytes=_png_bytes(), content_type="image/png")


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
    credit.image_balance = amount
    await db.commit()


async def test_generate_creates_pending_results_for_each_provider(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

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
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["image_balance"] == 80  # 10 per provider, both reserved up front


async def test_partial_reservation_is_rolled_back_when_second_provider_unaffordable(
    client, seeded_db, user_factory, monkeypatch
):
    """Free plan has 10 image credits; asking for two providers costs 20. The first provider's
    reservation must be given back rather than silently consumed."""
    user = await user_factory()
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 402

    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["image_balance"] == 10


async def test_both_providers_run_and_persist_images(client, seeded_db, user_factory, monkeypatch, fake_providers):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    fake_providers("ok", "ok")
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    # Give enough credits for two providers.
    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 100
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
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 100
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
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(resp.json()["id"]))

    credits = (await client.get("/api/v1/credits", headers=user["headers"])).json()
    assert credits["image_balance"] == 100  # both reserved then both refunded


async def test_providers_run_concurrently_not_sequentially(
    client, seeded_db, user_factory, monkeypatch, fake_providers
):
    """Two 0.2s providers must finish in well under 0.4s if they truly run in parallel."""
    import time

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    fake_providers(openai_behavior="slow", gemini_behavior="slow")
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

    from app.models.billing import Credit

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "x", "providers": ["openai", "gemini"]},
    )
    started = time.perf_counter()
    await image_orchestrator.run_generation(uuid.UUID(resp.json()["id"]))
    elapsed = time.perf_counter() - started
    assert elapsed < 0.38, f"providers appear to run sequentially ({elapsed:.2f}s)"


async def test_regenerate_creates_new_result_linked_to_parent(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)

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
