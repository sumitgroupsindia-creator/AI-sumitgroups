"""The product presents neutral "Model 1 / Model 2" slots. User-facing API responses must never
carry vendor model identifiers, otherwise the branding leaks through devtools even though the UI
hides it. Admin endpoints are explicitly exempt — administrators configure the providers."""
import uuid

from sqlalchemy import select

from app.models.billing import Credit
from app.models.chat import Conversation, Message
from app.models.image import GenerationRequest, GenerationResult
from app.models.user import User

VENDOR_MODEL_MARKERS = ("gpt-", "gemini-", "gpt_image", "o1-", "claude-")


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def test_generation_response_hides_vendor_model_id(client, seeded_db, user_factory, monkeypatch):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)
    resp = await client.post(
        "/api/v1/images/generate", headers=user["headers"],
        json={"prompt": "a cat", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 202

    body = resp.json()
    for result in body["results"]:
        assert "model" not in result, "vendor model id leaked into the user-facing generation response"

    lowered = resp.text.lower()
    for marker in VENDOR_MODEL_MARKERS:
        assert marker not in lowered, f"vendor marker {marker!r} leaked into generation response"


async def test_conversation_response_hides_vendor_model_id(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])

    conversation = Conversation(user_id=uid, title="Hi", model="gpt-4o-mini", provider="openai")
    seeded_db.add(conversation)
    await seeded_db.flush()
    seeded_db.add(Message(conversation_id=conversation.id, role="user", content="hello", model="gpt-4o-mini"))
    await seeded_db.commit()

    listing = await client.get("/api/v1/conversations", headers=user["headers"])
    assert "model" not in listing.json()[0]
    assert "gpt-" not in listing.text.lower()

    detail = await client.get(f"/api/v1/conversations/{conversation.id}", headers=user["headers"])
    assert "model" not in detail.json()
    assert "gpt-" not in detail.text.lower()
    for message in detail.json()["messages"]:
        assert "model" not in message


async def test_usage_response_hides_vendor_model_id(client, seeded_db, user_factory):
    from app.services.credit_service import record_usage

    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await record_usage(
        seeded_db, user_id=uid, request_id="r1", provider="openai", model="gpt-image-1",
        operation="image_generate", credits_consumed=10, status="success",
    )
    await seeded_db.commit()

    resp = await client.get("/api/v1/usage", headers=user["headers"])
    assert resp.status_code == 200
    assert "model" not in resp.json()[0]
    assert "gpt-image-1" not in resp.text


async def test_client_cannot_override_the_model(client, user_factory):
    """A caller must not be able to pick an arbitrary vendor model; the field is rejected/ignored
    and the server resolves the model from provider_configs."""
    user = await user_factory()
    resp = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "hi", "provider": "openai", "model": "gpt-4-turbo-preview"},
    )
    # The extra field is ignored rather than honoured — the request still succeeds.
    assert resp.status_code == 200
    assert "gpt-4-turbo-preview" not in resp.text


async def test_admin_still_sees_real_model_ids(client, seeded_db, user_factory):
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    db_user = (await seeded_db.execute(select(User).where(User.id == uid))).scalar_one()
    db_user.is_admin = True
    await seeded_db.commit()

    # Re-login so the token carries the admin claim.
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    headers = {"Authorization": f"Bearer {tokens.json()['access_token']}"}

    models = await client.get("/api/v1/admin/models", headers=headers)
    assert models.status_code == 200
    assert any("gpt-" in c["model"] or "gemini-" in c["model"] for c in models.json())

    gen = GenerationRequest(user_id=uid, prompt="p", status="failed", request_ref="ref")
    seeded_db.add(gen)
    await seeded_db.flush()
    seeded_db.add(
        GenerationResult(
            request_id=gen.id, provider="openai", model="gpt-image-1", status="failed", error="boom"
        )
    )
    await seeded_db.commit()

    failures = await client.get("/api/v1/admin/generations/failed", headers=headers)
    assert failures.status_code == 200
    assert failures.json()[0]["model"] == "gpt-image-1"
