"""The most important security tests: User A must never reach User B's data.

Every user-scoped resource is checked for read, update, delete and file access, and the expected
response is 404 (not 403) so the API never even confirms that another user's resource exists.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message
from app.models.image import GeneratedImage, GenerationRequest, GenerationResult, UploadedFile
from app.models.user import User
from sqlalchemy import select


async def _user_id(db: AsyncSession, email: str) -> uuid.UUID:
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


@pytest.fixture
async def two_users(user_factory):
    return await user_factory(), await user_factory()


async def test_user_cannot_read_another_users_conversation(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    conversation = Conversation(user_id=alice_id, title="Alice private", model="gpt-4o-mini", provider="openai")
    seeded_db.add(conversation)
    await seeded_db.commit()

    own = await client.get(f"/api/v1/conversations/{conversation.id}", headers=alice["headers"])
    assert own.status_code == 200

    stolen = await client.get(f"/api/v1/conversations/{conversation.id}", headers=bob["headers"])
    assert stolen.status_code == 404


async def test_user_cannot_rename_or_delete_another_users_conversation(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    conversation = Conversation(user_id=alice_id, title="Alice private", model="gpt-4o-mini", provider="openai")
    seeded_db.add(conversation)
    await seeded_db.commit()

    renamed = await client.patch(
        f"/api/v1/conversations/{conversation.id}", headers=bob["headers"], json={"title": "pwned"}
    )
    assert renamed.status_code == 404

    deleted = await client.delete(f"/api/v1/conversations/{conversation.id}", headers=bob["headers"])
    assert deleted.status_code == 404

    # And the record is untouched.
    await seeded_db.refresh(conversation)
    assert conversation.title == "Alice private"


async def test_conversation_list_only_returns_own_rows(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])
    seeded_db.add(Conversation(user_id=alice_id, title="Alice only", model="gpt-4o-mini", provider="openai"))
    await seeded_db.commit()

    bob_list = await client.get("/api/v1/conversations", headers=bob["headers"])
    assert bob_list.status_code == 200
    assert bob_list.json() == []

    alice_list = await client.get("/api/v1/conversations", headers=alice["headers"])
    assert len(alice_list.json()) == 1


async def test_user_cannot_read_another_users_messages(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    conversation = Conversation(user_id=alice_id, title="secrets", model="gpt-4o-mini", provider="openai")
    seeded_db.add(conversation)
    await seeded_db.flush()
    seeded_db.add(Message(conversation_id=conversation.id, role="user", content="my bank password is hunter2"))
    await seeded_db.commit()

    stolen = await client.get(f"/api/v1/conversations/{conversation.id}", headers=bob["headers"])
    assert stolen.status_code == 404
    assert "hunter2" not in stolen.text


async def test_user_cannot_read_another_users_generation(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    gen = GenerationRequest(user_id=alice_id, prompt="a private prompt", status="completed", request_ref="ref-1")
    seeded_db.add(gen)
    await seeded_db.commit()

    own = await client.get(f"/api/v1/images/{gen.id}", headers=alice["headers"])
    assert own.status_code == 200

    stolen = await client.get(f"/api/v1/images/{gen.id}", headers=bob["headers"])
    assert stolen.status_code == 404
    assert "a private prompt" not in stolen.text


async def test_image_list_only_returns_own_rows(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])
    seeded_db.add(GenerationRequest(user_id=alice_id, prompt="alice art", status="completed", request_ref="ref-2"))
    await seeded_db.commit()

    assert (await client.get("/api/v1/images", headers=bob["headers"])).json() == []
    assert len((await client.get("/api/v1/images", headers=alice["headers"])).json()) == 1


async def test_user_cannot_regenerate_another_users_generation(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])
    gen = GenerationRequest(user_id=alice_id, prompt="p", status="completed", request_ref="ref-3")
    seeded_db.add(gen)
    await seeded_db.commit()

    resp = await client.post(f"/api/v1/images/{gen.id}/regenerate", headers=bob["headers"], json={})
    assert resp.status_code == 404


async def test_user_cannot_download_another_users_generated_image(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    image = GeneratedImage(
        user_id=alice_id, stored_filename=f"{uuid.uuid4()}.png", thumbnail_filename=f"{uuid.uuid4()}.png",
        content_type="image/png", width=1024, height=1024, size_bytes=1234,
    )
    seeded_db.add(image)
    await seeded_db.commit()

    assert (await client.get(f"/api/v1/files/generated/{image.id}", headers=bob["headers"])).status_code == 404
    assert (await client.get(f"/api/v1/files/thumbnail/{image.id}", headers=bob["headers"])).status_code == 404


async def test_user_cannot_download_another_users_upload(client: AsyncClient, two_users, seeded_db):
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    upload = UploadedFile(
        user_id=alice_id, stored_filename=f"{uuid.uuid4()}.png", original_filename="private.png",
        content_type="image/png", size_bytes=100, width=10, height=10,
    )
    seeded_db.add(upload)
    await seeded_db.commit()

    assert (await client.get(f"/api/v1/files/uploaded/{upload.id}", headers=bob["headers"])).status_code == 404


async def test_user_cannot_generate_using_another_users_upload(client: AsyncClient, two_users, seeded_db):
    """An attacker must not be able to feed someone else's private photo into their own generation."""
    alice, bob = two_users
    alice_id = await _user_id(seeded_db, alice["email"])

    upload = UploadedFile(
        user_id=alice_id, stored_filename=f"{uuid.uuid4()}.png", original_filename="alice_face.png",
        content_type="image/png", size_bytes=100, width=10, height=10,
    )
    seeded_db.add(upload)
    await seeded_db.commit()

    resp = await client.post(
        "/api/v1/images/generate",
        headers=bob["headers"],
        json={"prompt": "use this face", "providers": ["openai"], "upload_file_id": str(upload.id)},
    )
    assert resp.status_code == 400


async def test_usage_records_are_not_shared(client: AsyncClient, two_users):
    alice, bob = two_users
    assert (await client.get("/api/v1/usage", headers=bob["headers"])).json() == []


async def test_non_admin_cannot_reach_admin_routes(client: AsyncClient, user_factory):
    user = await user_factory()
    for path in ["/api/v1/admin/stats", "/api/v1/admin/users", "/api/v1/admin/plans", "/api/v1/admin/models"]:
        resp = await client.get(path, headers=user["headers"])
        assert resp.status_code == 403, path


async def test_admin_routes_require_authentication(client: AsyncClient):
    assert (await client.get("/api/v1/admin/users")).status_code == 401


async def test_nonexistent_resource_returns_404_not_500(client: AsyncClient, user_factory):
    user = await user_factory()
    random_id = uuid.uuid4()
    assert (await client.get(f"/api/v1/conversations/{random_id}", headers=user["headers"])).status_code == 404
    assert (await client.get(f"/api/v1/images/{random_id}", headers=user["headers"])).status_code == 404
    assert (await client.get(f"/api/v1/files/generated/{random_id}", headers=user["headers"])).status_code == 404
