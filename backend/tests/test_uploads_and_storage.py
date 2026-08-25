import io
import os
import uuid

import pytest
from PIL import Image

from app.services.storage.local_storage import LocalStorageProvider, PathTraversalError
from app.utils.file_validation import FileValidationError, re_encode_image
from app.core.config import get_settings
from app.services import settings_service


def _image_bytes(fmt="PNG", size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buf, format=fmt)
    return buf.getvalue()


# ---------- upload validation ----------


async def test_upload_accepts_valid_png(client, seeded_db, user_factory, monkeypatch, tmp_path):
    from sqlalchemy import select

    from app.models.billing import Credit
    from app.models.user import User

    user = await user_factory()
    uid = (await seeded_db.execute(select(User).where(User.email == user["email"]))).scalar_one().id
    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == uid))).scalar_one()
    credit.image_balance = 100
    await seeded_db.commit()

    monkeypatch.setattr("app.api.v1.images.run_generation_task.delay", lambda *a, **kw: None)
    monkeypatch.setattr(
        "app.services.upload_service.get_storage_provider", lambda: LocalStorageProvider(str(tmp_path))
    )

    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("photo.png", _image_bytes("PNG"), "image/png")},
        data={"prompt": "make it cinematic", "providers": "openai"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["prompt"] == "make it cinematic"

    saved = os.listdir(tmp_path / "images" / "uploaded")
    assert len(saved) == 1
    # The stored name must be a server-generated UUID, never the client's filename.
    assert "photo" not in saved[0]
    uuid.UUID(saved[0].rsplit(".", 1)[0])


async def test_upload_rejects_disallowed_extension(client, user_factory):
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["error"]


async def test_upload_rejects_non_image_disguised_as_png(client, user_factory):
    """A PHP/script payload renamed to .png must be rejected by content sniffing, not trusted by name."""
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("payload.png", b"<?php system($_GET['c']); ?>", "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400
    assert "not a valid image" in resp.json()["error"]


async def test_upload_rejects_extension_content_mismatch(client, user_factory):
    """Real JPEG bytes with a .png extension: content and extension must agree."""
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("mismatch.png", _image_bytes("JPEG"), "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400
    assert "does not match" in resp.json()["error"]


async def test_upload_rejects_oversized_file(client, user_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    settings_service.invalidate()
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("big.png", _image_bytes("PNG"), "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400
    assert "limit" in resp.json()["error"]


async def test_upload_rejects_oversized_dimensions(client, user_factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_image_dimension", 32)
    settings_service.invalidate()
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("big.png", _image_bytes("PNG", size=(64, 64)), "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400
    assert "dimensions" in resp.json()["error"]


async def test_upload_rejects_empty_file(client, user_factory):
    user = await user_factory()
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        headers=user["headers"],
        files={"file": ("empty.png", b"", "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 400


async def test_upload_requires_authentication(client):
    resp = await client.post(
        "/api/v1/images/generate-with-upload",
        files={"file": ("photo.png", _image_bytes(), "image/png")},
        data={"prompt": "x", "providers": "openai"},
    )
    assert resp.status_code == 401


def test_re_encode_strips_trailing_payload():
    """Re-encoding removes anything appended after the image data (polyglot file defence)."""
    original = _image_bytes("PNG")
    tainted = original + b"<?php system($_GET['c']); ?>"
    cleaned = re_encode_image(tainted, "image/png")
    assert b"<?php" not in cleaned
    with Image.open(io.BytesIO(cleaned)) as img:
        assert img.size == (64, 64)


# ---------- storage path safety ----------


def test_storage_rejects_path_traversal_in_filename(tmp_path):
    storage = LocalStorageProvider(str(tmp_path))
    for bad in ["../escape.png", "../../etc/passwd", "sub/dir.png", "..", "."]:
        with pytest.raises(PathTraversalError):
            storage.resolve_path("images/generated", bad)


def test_storage_rejects_unknown_subdir(tmp_path):
    storage = LocalStorageProvider(str(tmp_path))
    with pytest.raises(PathTraversalError):
        storage.resolve_path("../../root", "x.png")
    with pytest.raises(PathTraversalError):
        storage.resolve_path("etc", "passwd")


async def test_storage_round_trip(tmp_path):
    storage = LocalStorageProvider(str(tmp_path))
    data = _image_bytes()
    name = f"{uuid.uuid4()}.png"

    await storage.save("images/generated", name, data)
    assert await storage.read("images/generated", name) == data

    await storage.delete("images/generated", name)
    with pytest.raises(FileNotFoundError):
        await storage.read("images/generated", name)


async def test_storage_read_missing_file_raises(tmp_path):
    storage = LocalStorageProvider(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        await storage.read("images/generated", f"{uuid.uuid4()}.png")


async def test_standalone_upload_returns_an_id_usable_as_a_chat_attachment(
    client, seeded_db, user_factory, monkeypatch, tmp_path
):
    """Chat attachments need an upload that exists before any generation does."""
    monkeypatch.setattr(
        "app.services.upload_service.get_storage_provider", lambda: LocalStorageProvider(str(tmp_path))
    )
    user = await user_factory()

    resp = await client.post(
        "/api/v1/files/upload",
        headers=user["headers"],
        files={"file": ("photo.png", _image_bytes("PNG"), "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content_type"] == "image/png"
    assert body["original_filename"] == "photo.png"
    assert body["id"]


async def test_standalone_upload_rejects_a_non_image(client, user_factory, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.upload_service.get_storage_provider", lambda: LocalStorageProvider(str(tmp_path))
    )
    user = await user_factory()

    resp = await client.post(
        "/api/v1/files/upload",
        headers=user["headers"],
        files={"file": ("payload.png", b"not an image at all", "image/png")},
    )
    assert resp.status_code == 400
