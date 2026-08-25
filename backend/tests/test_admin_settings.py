"""Runtime configuration managed from the admin panel.

Two properties matter most here and are asserted directly: a stored secret is never handed back in
readable form, and a blank submission does not wipe a secret the form simply could not display.
"""
from sqlalchemy import select

from app.core.config import get_settings
from app.models.settings import AppSetting
from app.models.user import User
from app.services import settings_service

SECRET = "sk-live-abcdefghijklmnop9876"


async def _admin_headers(client, seeded_db, user_factory):
    user = await user_factory()
    db_user = (await seeded_db.execute(select(User).where(User.email == user["email"]))).scalar_one()
    db_user.is_admin = True
    await seeded_db.commit()
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    return {"Authorization": f"Bearer {tokens.json()['access_token']}"}, db_user.email


async def test_secret_is_stored_encrypted_and_never_returned_in_the_clear(
    client, seeded_db, user_factory
):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)

    saved = await client.put(
        "/api/v1/admin/settings", headers=headers, json={"values": {"openai_api_key": SECRET}}
    )
    assert saved.status_code == 200

    entry = next(s for s in saved.json() if s["key"] == "openai_api_key")
    assert entry["value"] == ""  # never echoed back
    assert entry["masked"].endswith(SECRET[-4:])
    assert SECRET not in saved.text
    assert entry["is_set"] is True
    assert entry["source"] == "database"

    row = (
        await seeded_db.execute(select(AppSetting).where(AppSetting.key == "openai_api_key"))
    ).scalar_one()
    assert SECRET not in row.value  # at rest it is sealed, not merely hidden by the API
    assert row.is_secret is True


async def test_blank_submission_leaves_an_existing_secret_untouched(client, seeded_db, user_factory):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)
    await client.put(
        "/api/v1/admin/settings", headers=headers, json={"values": {"gemini_api_key": SECRET}}
    )

    # The form cannot show the current value, so an untouched field posts as empty. That must not
    # be read as "clear it".
    again = await client.put(
        "/api/v1/admin/settings", headers=headers, json={"values": {"gemini_api_key": ""}}
    )
    entry = next(s for s in again.json() if s["key"] == "gemini_api_key")
    assert entry["is_set"] is True
    assert entry["masked"].endswith(SECRET[-4:])


async def test_saved_value_overrides_the_environment(client, seeded_db, user_factory):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)
    assert get_settings().rate_limit_per_minute != 7

    await client.put(
        "/api/v1/admin/settings", headers=headers, json={"values": {"rate_limit_per_minute": "7"}}
    )
    assert await settings_service.get_int("rate_limit_per_minute") == 7


async def test_audit_trail_records_the_change_without_the_secret(client, seeded_db, user_factory):
    headers, email = await _admin_headers(client, seeded_db, user_factory)
    await client.put(
        "/api/v1/admin/settings", headers=headers, json={"values": {"smtp_password": SECRET}}
    )

    audit = await client.get("/api/v1/admin/settings/audit", headers=headers)
    assert audit.status_code == 200
    assert SECRET not in audit.text

    entry = next(a for a in audit.json() if a["key"] == "smtp_password")
    assert entry["actor_email"] == email
    assert entry["new_preview"].endswith(SECRET[-4:])


async def test_keys_outside_the_catalog_are_ignored(client, seeded_db, user_factory):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)
    resp = await client.put(
        "/api/v1/admin/settings",
        headers=headers,
        json={"values": {"database_url": "mysql://attacker/db", "jwt_secret": "hijacked"}},
    )
    assert resp.status_code == 200
    assert {"database_url", "jwt_secret"}.isdisjoint({s["key"] for s in resp.json()})

    rows = (await seeded_db.execute(select(AppSetting))).scalars().all()
    assert {"database_url", "jwt_secret"}.isdisjoint({r.key for r in rows})


async def test_settings_are_admin_only(client, user_factory):
    user = await user_factory()
    assert (await client.get("/api/v1/admin/settings", headers=user["headers"])).status_code == 403
    assert (
        await client.put(
            "/api/v1/admin/settings", headers=user["headers"], json={"values": {"smtp_host": "evil"}}
        )
    ).status_code == 403


async def test_renaming_a_slot_reaches_the_public_endpoint(client, seeded_db, user_factory):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)

    brands = await client.get("/api/v1/admin/brands", headers=headers)
    openai_brand = next(b for b in brands.json() if b["provider"] == "openai")
    assert openai_brand["slot"] == "Model 1"

    renamed = await client.patch(
        f"/api/v1/admin/brands/{openai_brand['id']}",
        headers=headers,
        json={"slot": "Sumit AI", "tier": "Everyday"},
    )
    assert renamed.status_code == 200

    public = await client.get("/api/v1/config/models")
    assert public.status_code == 200
    slot = next(s for s in public.json() if s["provider"] == "openai")
    assert slot["slot"] == "Sumit AI"
    assert slot["tier"] == "Everyday"


async def test_public_model_endpoint_never_leaks_vendor_model_ids(client, seeded_db):
    resp = await client.get("/api/v1/config/models")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    for marker in ("gpt-", "gemini-2", "gpt-image"):
        assert marker not in resp.text


async def test_admin_can_rename_the_provider_display_name(client, seeded_db, user_factory):
    headers, _ = await _admin_headers(client, seeded_db, user_factory)
    configs = await client.get("/api/v1/admin/models", headers=headers)
    config = configs.json()[0]

    updated = await client.patch(
        f"/api/v1/admin/models/{config['id']}", headers=headers, json={"display_name": "Primary"}
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Primary"
