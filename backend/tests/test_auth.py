import pytest
from httpx import AsyncClient


async def test_register_returns_tokens_and_seeds_free_plan_credits(client: AsyncClient, user_factory):
    user = await user_factory()
    assert user["access_token"]

    me = await client.get("/api/v1/user/me", headers=user["headers"])
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]
    assert me.json()["is_admin"] is False

    credits = await client.get("/api/v1/credits", headers=user["headers"])
    assert credits.status_code == 200
    assert credits.json() == {"balance": 10}


async def test_register_rejects_duplicate_email(client: AsyncClient, user_factory):
    user = await user_factory()
    resp = await client.post(
        "/api/v1/auth/register", json={"email": user["email"], "password": "password123"}
    )
    assert resp.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={"email": "short@example.com", "password": "abc"})
    assert resp.status_code == 422


async def test_login_success_and_failure(client: AsyncClient, user_factory):
    user = await user_factory()

    ok = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": user["password"]})
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    bad = await client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrongpassword"})
    assert bad.status_code == 401
    # The error must not disclose whether the email exists.
    assert "Invalid email or password" in bad.json()["error"]

    missing = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "password123"})
    assert missing.status_code == 401


async def test_refresh_token_flow(client: AsyncClient, user_factory):
    user = await user_factory()
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_access_token_rejected_as_refresh_token(client: AsyncClient, user_factory):
    user = await user_factory()
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": user["access_token"]})
    assert resp.status_code == 401


async def test_protected_routes_require_auth(client: AsyncClient):
    for path in ["/api/v1/user/me", "/api/v1/credits", "/api/v1/conversations", "/api/v1/images"]:
        resp = await client.get(path)
        assert resp.status_code == 401, path


async def test_garbage_token_rejected(client: AsyncClient):
    resp = await client.get("/api/v1/user/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


async def test_forgot_password_does_not_leak_account_existence(client: AsyncClient, user_factory):
    user = await user_factory()
    known = await client.post("/api/v1/auth/forgot-password", json={"email": user["email"]})
    unknown = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def test_reset_password_with_invalid_token_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/reset-password", json={"token": "invalid-token", "new_password": "newpassword123"}
    )
    assert resp.status_code == 400


async def test_profile_update(client: AsyncClient, user_factory):
    user = await user_factory()
    resp = await client.patch("/api/v1/user/me", headers=user["headers"], json={"full_name": "Renamed User"})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Renamed User"
