"""Chat answering through one or two model slots, with an optional image on the turn.

The behaviours worth pinning: both models answer the same turn independently, neither is replayed
the other's words, the model id comes from provider_configs rather than the environment, and an
attached image actually reaches the provider.
"""
import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.billing import Credit
from app.models.chat import Conversation, Message
from app.models.image import GenerationRequest, ProviderConfig, UploadedFile
from app.models.user import User
from app.providers.base import ProviderError
from app.services import chat_service, prompt_service
from app.services.storage.local_storage import get_storage_provider


def _png_bytes(color=(0, 128, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


async def _user_id(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


async def _top_up(db, uid, amount=100):
    credit = (await db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = amount
    await db.commit()


class _FakeChatProvider:
    """Records what it was asked, so a test can assert on the messages that reached the vendor."""

    def __init__(self, name, behavior="ok", routes_to="0"):
        self.name = name
        self._behavior = behavior
        self._routes_to = routes_to
        self.seen_messages = None
        self.seen_model = None
        self.seen_system = None
        self.completions = []

    async def stream_chat(self, messages, model, system=None):
        self.seen_messages = messages
        self.seen_model = model
        self.seen_system = system
        if self._behavior == "fail":
            raise ProviderError(self.name, "simulated outage", retryable=False)
        yield f"[{self.name}] "
        yield "answer"

    async def complete(self, messages, model, system=None, max_tokens=256):
        """The router and the photo-reader both land here. Answering "0" means no task template
        matched, which keeps a test's system prompt to the base unless it asks otherwise."""
        self.completions.append({"messages": messages, "system": system, "max_tokens": max_tokens})
        return self._routes_to


@pytest.fixture
def fake_chat(monkeypatch):
    registry: dict[str, _FakeChatProvider] = {}

    def _install(openai_behavior="ok", gemini_behavior="ok", routes_to="0"):
        registry["openai"] = _FakeChatProvider("openai", openai_behavior, routes_to)
        registry["gemini"] = _FakeChatProvider("gemini", gemini_behavior, routes_to)
        # Patched in both modules: the streamed answer comes through chat_service, while the router
        # and the photo-reader reach for a provider from prompt_service.
        monkeypatch.setattr(chat_service, "get_chat_provider", lambda name: registry[name])
        monkeypatch.setattr(prompt_service, "get_chat_provider", lambda name: registry[name])
        return registry

    return _install


def _events(body: str, name: str) -> list[str]:
    """The data lines of every SSE event of the given type."""
    out = []
    for block in body.split("\n\n"):
        if block.startswith(f"event: {name}\n"):
            out.append(block.split("data: ", 1)[1])
    return out


async def test_model_id_comes_from_provider_config_not_the_environment(
    client, seeded_db, user_factory, fake_chat
):
    providers = fake_chat()
    user = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, user["email"]))

    config = (
        await seeded_db.execute(
            select(ProviderConfig).where(
                ProviderConfig.provider == "openai", ProviderConfig.capability == "chat"
            )
        )
    ).scalar_one()
    config.model = "model-set-by-admin"
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hi", "providers": ["openai"]}
    )
    assert resp.status_code == 200
    assert providers["openai"].seen_model == "model-set-by-admin"


async def test_both_models_answer_the_same_turn(client, seeded_db, user_factory, fake_chat):
    fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    resp = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "write a caption", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 200

    deltas = " ".join(_events(resp.text, "delta"))
    assert '"provider": "openai"' in deltas
    assert '"provider": "gemini"' in deltas
    assert len(_events(resp.text, "provider_done")) == 2

    # Taken from the response, not "the first conversation in the table": the suite shares one
    # database across tests, so a bare select would pick up an earlier test's row.
    conversation_id = _events(resp.text, "done")[0].split('"conversation_id": "')[1].split('"')[0]
    conversation = (
        await seeded_db.execute(select(Conversation).where(Conversation.id == uuid.UUID(conversation_id)))
    ).scalar_one()
    assistants = (
        (
            await seeded_db.execute(
                select(Message).where(
                    Message.conversation_id == conversation.id, Message.role == "assistant"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {m.provider for m in assistants} == {"openai", "gemini"}


async def test_neither_model_is_replayed_the_other_s_words(client, seeded_db, user_factory, fake_chat):
    providers = fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    first = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "turn one", "providers": ["openai", "gemini"]},
    )
    conversation_id = _events(first.text, "done")[0].split('"conversation_id": "')[1].split('"')[0]

    await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={
            "conversation_id": conversation_id,
            "message": "turn two",
            "providers": ["openai", "gemini"],
        },
    )

    openai_saw = [m.content for m in providers["openai"].seen_messages if m.role == "assistant"]
    gemini_saw = [m.content for m in providers["gemini"].seen_messages if m.role == "assistant"]
    assert all("[openai]" in c for c in openai_saw)
    assert all("[gemini]" in c for c in gemini_saw)
    assert openai_saw and gemini_saw  # each did get its own history back


async def test_two_models_cost_two_slots_and_a_failure_refunds_only_its_own(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat(gemini_behavior="fail")
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid, amount=10)

    resp = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "hi", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 200
    assert any('"provider": "gemini"' in e for e in _events(resp.text, "error"))

    await seeded_db.commit()  # see what the streaming sessions committed
    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    await seeded_db.refresh(credit)
    # Two reserved, the failed one refunded: exactly one slot paid for.
    assert credit.balance == 9


async def test_unaffordable_pair_is_refused_before_either_model_runs(
    client, seeded_db, user_factory, fake_chat
):
    providers = fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid, amount=1)  # enough for one slot, not two

    resp = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={"message": "hi", "providers": ["openai", "gemini"]},
    )
    assert resp.status_code == 200
    assert any("insufficient_credits" in e for e in _events(resp.text, "error"))
    assert providers["openai"].seen_messages is None
    assert providers["gemini"].seen_messages is None


async def test_attached_image_reaches_the_provider(client, seeded_db, user_factory, fake_chat):
    providers = fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    stored_name = f"{uuid.uuid4()}.png"
    await get_storage_provider().save("images/uploaded", stored_name, _png_bytes())
    uploaded = UploadedFile(
        user_id=uid,
        stored_filename=stored_name,
        original_filename="product.png",
        content_type="image/png",
        size_bytes=100,
    )
    seeded_db.add(uploaded)
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/chat/stream",
        headers=user["headers"],
        json={
            "message": "write an Instagram caption for this",
            "providers": ["openai"],
            "upload_file_id": str(uploaded.id),
        },
    )
    assert resp.status_code == 200

    sent = providers["openai"].seen_messages
    with_image = [m for m in sent if m.image is not None]
    assert len(with_image) == 1, "only the current turn should carry the image"
    assert with_image[0].role == "user"
    assert with_image[0].image.mime_type == "image/png"
    assert with_image[0].image.data == _png_bytes()


async def test_attachment_belonging_to_someone_else_is_refused(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat()
    owner = await user_factory()
    intruder = await user_factory()
    owner_id = await _user_id(seeded_db, owner["email"])
    await _top_up(seeded_db, await _user_id(seeded_db, intruder["email"]))

    uploaded = UploadedFile(
        user_id=owner_id,
        stored_filename=f"{uuid.uuid4()}.png",
        original_filename="private.png",
        content_type="image/png",
        size_bytes=100,
    )
    seeded_db.add(uploaded)
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/chat/stream",
        headers=intruder["headers"],
        json={"message": "what is this", "providers": ["openai"], "upload_file_id": str(uploaded.id)},
    )
    assert resp.status_code == 404


async def test_image_generated_from_a_conversation_is_returned_in_its_thread(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat()
    user = await user_factory()
    uid = await _user_id(seeded_db, user["email"])
    await _top_up(seeded_db, uid)

    started = await client.post(
        "/api/v1/chat/stream", headers=user["headers"], json={"message": "hello", "providers": ["openai"]}
    )
    conversation_id = _events(started.text, "done")[0].split('"conversation_id": "')[1].split('"')[0]

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    created = await client.post(
        "/api/v1/images/generate",
        headers=user["headers"],
        json={
            "prompt": "a product photo on a marble table",
            "providers": ["openai"],
            "conversation_id": conversation_id,
        },
    )
    assert created.status_code == 202
    assert created.json()["conversation_id"] == conversation_id

    thread = await client.get(f"/api/v1/conversations/{conversation_id}", headers=user["headers"])
    assert thread.status_code == 200
    body = thread.json()
    assert len(body["generations"]) == 1
    assert body["generations"][0]["prompt"] == "a product photo on a marble table"
    assert len(body["messages"]) >= 2


async def test_generation_cannot_be_attached_to_someone_else_s_conversation(
    client, seeded_db, user_factory, fake_chat
):
    fake_chat()
    owner = await user_factory()
    intruder = await user_factory()
    await _top_up(seeded_db, await _user_id(seeded_db, owner["email"]))

    started = await client.post(
        "/api/v1/chat/stream", headers=owner["headers"], json={"message": "mine", "providers": ["openai"]}
    )
    conversation_id = _events(started.text, "done")[0].split('"conversation_id": "')[1].split('"')[0]

    intruder_id = await _user_id(seeded_db, intruder["email"])
    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == intruder_id))).scalar_one()
    credit.balance = 100
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate",
        headers=intruder["headers"],
        json={"prompt": "x", "providers": ["openai"], "conversation_id": conversation_id},
    )
    assert resp.status_code == 400

    generations = (
        (await seeded_db.execute(select(GenerationRequest).where(GenerationRequest.user_id == intruder_id)))
        .scalars()
        .all()
    )
    assert generations == []
