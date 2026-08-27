"""The instructions the product wraps around every request.

What matters here is not the wording — that is editable — but that the wrapping happens, that a
customer's own words survive it, and that when a helper call fails the answer still arrives.
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.billing import Credit, UsageRecord
from app.models.prompt import PromptTemplate
from app.models.user import User
from app.providers.base import ProviderError
from app.services import chat_service, image_orchestrator, image_service, prompt_service


class _FakeChat:
    """Stands in for both roles a chat model plays here: answering the customer, and answering the
    router or the photo-reader."""

    def __init__(self, answer="0", fail_complete=False):
        self._answer = answer
        self._fail_complete = fail_complete
        self.systems: list[str | None] = []
        self.completions: list[dict] = []

    async def stream_chat(self, messages, model, system=None, usage=None):
        self.systems.append(system)
        yield "ok"

    async def complete(self, messages, model, system=None, max_tokens=256, usage=None):
        if self._fail_complete:
            raise ProviderError("fake", "router is down", retryable=False)
        self.completions.append({"messages": messages, "system": system, "max_tokens": max_tokens})
        return self._answer


class _FakeImage:
    def __init__(self):
        self.prompts: list[str] = []
        self.aspects: list[str] = []

    async def generate_image(self, prompt, model, input_image=None, input_mime=None, aspect="portrait"):
        self.prompts.append(prompt)
        self.aspects.append(aspect)
        raise ProviderError("fake", "stop here — the prompt is what this test is about", retryable=False)


@pytest.fixture
def fake_chat(monkeypatch):
    def _install(answer="0", fail_complete=False):
        provider = _FakeChat(answer, fail_complete)
        monkeypatch.setattr(chat_service, "get_chat_provider", lambda name: provider)
        monkeypatch.setattr(prompt_service, "get_chat_provider", lambda name: provider)
        return provider

    return _install


@pytest.fixture
def fake_image(monkeypatch):
    def _install():
        provider = _FakeImage()
        monkeypatch.setattr(image_service, "get_image_provider", lambda name: provider)
        return provider

    return _install


@pytest_asyncio.fixture
async def restore_templates(seeded_db):
    """Templates are shared across the session, so anything a test disables is switched back on."""
    columns = ("is_enabled", "content", "description")
    before = {
        row.id: {c: getattr(row, c) for c in columns}
        for row in (await seeded_db.execute(select(PromptTemplate))).scalars().all()
    }
    yield
    seeded_db.expire_all()
    for row in (await seeded_db.execute(select(PromptTemplate))).scalars().all():
        for column, value in before.get(row.id, {}).items():
            setattr(row, column, value)
    await seeded_db.commit()


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _top_up(db, uid, amount=100):
    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = amount
    await db.commit()


async def _disable(db, key):
    row = (await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))).scalar_one()
    row.is_enabled = False
    await db.commit()


# --------------------------------------------------------------------------- chat


async def test_chat_carries_the_house_identity(client, seeded_db, user_factory, fake_chat):
    provider = fake_chat()
    user = await user_factory()

    await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hi", "providers": ["openai"]}
    )

    assert provider.systems, "the model was never given a system prompt"
    assert "Sumit Groups" in provider.systems[0]


async def test_a_routed_task_is_appended_to_the_base(client, seeded_db, user_factory, fake_chat):
    """Answering "1" picks the first task template, which is added on top of the base — not
    instead of it."""
    provider = fake_chat(answer="1")
    user = await user_factory()

    await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "ek kahani likho", "providers": ["openai"]},
    )

    system = provider.systems[0]
    assert "Sumit Groups" in system
    assert "Write the piece itself" in system


async def test_no_match_leaves_only_the_base(client, seeded_db, user_factory, fake_chat):
    provider = fake_chat(answer="0")
    user = await user_factory()

    await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hello", "providers": ["openai"]}
    )

    assert "Write the piece itself" not in provider.systems[0]


async def test_a_number_the_model_invented_is_ignored(client, seeded_db, user_factory, fake_chat):
    """The router is a language model; it can answer 47. That must not index into anything."""
    provider = fake_chat(answer="47")
    user = await user_factory()

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hello", "providers": ["openai"]}
    )
    assert resp.status_code == 200
    assert "Write the piece itself" not in provider.systems[0]


async def test_a_broken_router_does_not_break_the_answer(client, seeded_db, user_factory, fake_chat):
    provider = fake_chat(fail_complete=True)
    user = await user_factory()

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hello", "providers": ["openai"]}
    )

    assert resp.status_code == 200
    assert "ok" in resp.text  # the model still answered
    assert "Sumit Groups" in provider.systems[0]  # on the base prompt alone


async def test_routing_is_paid_for_once_even_with_two_slots(
    client, seeded_db, user_factory, fake_chat
):
    """Both models answer the same request, so the style is chosen once and billed once."""
    provider = fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "hello", "providers": ["openai", "gemini"]},
    )

    assert len(provider.completions) == 1
    await seeded_db.commit()
    routes = (
        await seeded_db.execute(
            select(UsageRecord).where(
                UsageRecord.user_id == uid, UsageRecord.operation == "assist_route"
            )
        )
    ).scalars().all()
    assert len(routes) == 1
    assert routes[0].credits_consumed == 0  # spent from the margin, never billed on
    assert routes[0].cost_inr > Decimal(0)


async def test_disabling_the_router_skips_the_call_entirely(
    client, seeded_db, user_factory, fake_chat, restore_templates
):
    """This is the cost switch: off means no extra API call, not merely no task chosen."""
    provider = fake_chat(answer="1")
    await _disable(seeded_db, "task_router")
    user = await user_factory()

    await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "kahani", "providers": ["openai"]}
    )

    assert provider.completions == []
    assert "Write the piece itself" not in provider.systems[0]


async def test_disabling_the_base_leaves_the_turn_unwrapped(
    client, seeded_db, user_factory, fake_chat, restore_templates
):
    provider = fake_chat()
    await _disable(seeded_db, "chat_base")
    user = await user_factory()

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hi", "providers": ["openai"]}
    )

    assert resp.status_code == 200
    assert provider.systems[0] is None


# --------------------------------------------------------------------------- image


async def test_image_prompt_is_wrapped_and_keeps_the_customers_words(
    client, seeded_db, user_factory, fake_chat, fake_image
):
    fake_chat()
    image = fake_image()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    created = await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={"prompt": "diwali poster with 50% off", "providers": ["openai"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    sent = image.prompts[0]
    assert "ready-to-post" in sent  # the house style
    assert "diwali poster with 50% off" in sent  # and the customer's own words, intact
    assert sent.index("ready-to-post") < sent.index("diwali poster")  # house style first


async def test_images_are_portrait_by_default(client, seeded_db, user_factory, fake_chat, fake_image):
    """Almost everything made here is posted to a phone."""
    fake_chat()
    image = fake_image()
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "x", "providers": ["openai"]}
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    assert image.aspects[0] == "portrait"
    assert "9:16" in image.prompts[0]  # Gemini has no size parameter, so it has to be in words


async def test_an_attached_photo_is_read_before_anything_is_drawn(
    client, seeded_db, user_factory, fake_chat, fake_image
):
    fake_chat(answer="a matte black steel bottle with a bamboo lid")
    image = fake_image()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 10, 10)).save(buf, format="PNG")
    upload = await client.post(
        "/api/v1/files/upload",
        headers=user["headers"],
        files={"file": ("bottle.png", buf.getvalue(), "image/png")},
    )
    assert upload.status_code == 201, upload.text

    created = await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={
            "prompt": "put it on a marble table",
            "providers": ["openai"],
            "upload_file_id": upload.json()["id"],
        },
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    assert "matte black steel bottle" in image.prompts[0]

    await seeded_db.commit()
    vision = (
        await seeded_db.execute(
            select(UsageRecord).where(
                UsageRecord.user_id == uid, UsageRecord.operation == "assist_vision"
            )
        )
    ).scalars().all()
    assert len(vision) == 1
    assert vision[0].credits_consumed == 0


async def test_no_photo_means_no_vision_call(client, seeded_db, user_factory, fake_chat, fake_image):
    fake_chat()
    fake_image()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    created = await client.post(
        "/api/v1/images/generate", headers=user["headers"], json={"prompt": "x", "providers": ["openai"]}
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    await seeded_db.commit()
    vision = (
        await seeded_db.execute(
            select(UsageRecord).where(
                UsageRecord.user_id == uid, UsageRecord.operation == "assist_vision"
            )
        )
    ).scalars().all()
    assert vision == []


async def test_disabling_the_photo_reader_skips_it(
    client, seeded_db, user_factory, fake_chat, fake_image, restore_templates
):
    fake_chat(answer="a bottle")
    image = fake_image()
    await _disable(seeded_db, "image_vision_brief")
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))

    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 10, 10)).save(buf, format="PNG")
    upload = await client.post(
        "/api/v1/files/upload",
        headers=user["headers"],
        files={"file": ("bottle.png", buf.getvalue(), "image/png")},
    )
    created = await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={"prompt": "x", "providers": ["openai"], "upload_file_id": upload.json()["id"]},
    )
    await image_orchestrator.run_generation(uuid.UUID(created.json()["id"]))

    assert "The photo provided shows" not in image.prompts[0]


# --------------------------------------------------------------------------- admin


async def test_admin_can_reword_a_template_and_the_next_turn_uses_it(
    client, seeded_db, user_factory, fake_chat, restore_templates
):
    provider = fake_chat()
    admin = await user_factory()
    db_user = (await seeded_db.execute(select(User).where(User.email == admin["email"]))).scalar_one()
    db_user.is_admin = True
    await seeded_db.commit()
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": admin["email"], "password": admin["password"]}
    )
    headers = {"Authorization": f"Bearer {tokens.json()['access_token']}"}

    rows = (await client.get("/api/v1/admin/prompts", headers=headers)).json()
    base = next(r for r in rows if r["key"] == "chat_base")
    saved = await client.patch(
        f"/api/v1/admin/prompts/{base['id']}",
        headers=headers,
        json={"content": "You are the assistant of a completely different shop."},
    )
    assert saved.status_code == 200

    user = await user_factory()
    await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hi", "providers": ["openai"]}
    )
    assert "completely different shop" in provider.systems[0]


async def test_key_scope_and_kind_cannot_be_edited(client, seeded_db, user_factory):
    """They are what the code looks a template up by. A text box must not be able to detach a row
    from the thing that reads it."""
    admin = await user_factory()
    db_user = (await seeded_db.execute(select(User).where(User.email == admin["email"]))).scalar_one()
    db_user.is_admin = True
    await seeded_db.commit()
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": admin["email"], "password": admin["password"]}
    )
    headers = {"Authorization": f"Bearer {tokens.json()['access_token']}"}

    rows = (await client.get("/api/v1/admin/prompts", headers=headers)).json()
    base = next(r for r in rows if r["key"] == "chat_base")

    updated = await client.patch(
        f"/api/v1/admin/prompts/{base['id']}",
        headers=headers,
        json={"key": "hijacked", "scope": "image", "kind": "task"},
    )
    assert updated.status_code == 200
    assert updated.json()["key"] == "chat_base"
    assert updated.json()["scope"] == "chat"
    assert updated.json()["kind"] == "base"
