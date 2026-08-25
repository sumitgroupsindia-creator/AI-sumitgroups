
import os
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("JWT_SECRET", "test_secret_for_tests_only_not_production")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("STORAGE_PATH", "./storage_test")
# Env vars win over .env: the limiter would otherwise throttle the suite itself. It has its own
# dedicated test that re-enables it.
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app.core.db import Base, get_db_session  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.image import ProviderConfig  # noqa: E402
from app.models.billing import Plan  # noqa: E402

# Must point at a schema dedicated to tests: the suite DROPs and recreates every table, so aiming
# it at a development database would silently destroy that data.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "mysql+aiomysql://test:test@127.0.0.1:53306/ai_saas_test?charset=utf8mb4"
)


SYNC_TEST_DATABASE_URL = TEST_DATABASE_URL.replace("mysql+aiomysql://", "mysql+pymysql://")


@pytest.fixture(scope="session", autouse=True)
def create_schema():
    """Builds the schema once with a *sync* engine. Doing this synchronously avoids sharing an
    async engine (and its bound event loop) across function-scoped async tests."""
    from sqlalchemy import create_engine, text

    eng = create_engine(SYNC_TEST_DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    eng.dispose()
    yield


@pytest_asyncio.fixture
async def engine(create_schema):
    # READ COMMITTED so a test's own session sees rows the app committed on a different session;
    # MySQL's default REPEATABLE READ would pin the test to a pre-request snapshot.
    eng = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True, isolation_level="READ COMMITTED")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Ensures the plans/provider_configs rows the app depends on exist."""
    from sqlalchemy import select

    existing = (await db_session.execute(select(Plan).where(Plan.code == "free"))).scalar_one_or_none()
    if existing is None:
        db_session.add_all(
            [
                Plan(code="free", name="Free", price=0, currency="INR", monthly_chat_credits=50,
                     monthly_image_credits=10, max_upload_mb=5),
                Plan(code="pro", name="Pro", price=999, currency="INR", monthly_chat_credits=1000,
                     monthly_image_credits=200, max_upload_mb=10),
            ]
        )
        db_session.add_all(
            [
                ProviderConfig(provider="openai", capability="chat", model="gpt-4o-mini",
                               credit_cost=1, display_name="OpenAI"),
                ProviderConfig(provider="gemini", capability="chat", model="gemini-2.0-flash",
                               credit_cost=1, display_name="Gemini"),
                ProviderConfig(provider="openai", capability="image", model="gpt-image-1",
                               credit_cost=10, display_name="OpenAI"),
                ProviderConfig(provider="gemini", capability="image", model="gemini-2.5-flash-image",
                               credit_cost=10, display_name="Gemini"),
            ]
        )
        await db_session.commit()
    return db_session


@pytest_asyncio.fixture
async def client(engine, seeded_db) -> AsyncIterator[AsyncClient]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db

    # The chat/image services open their own sessions via AsyncSessionLocal; point that at the
    # test engine too so background work in tests hits the same database.
    import app.core.db as core_db
    import app.services.chat_service as chat_service
    import app.services.image_service as image_service
    import app.services.image_orchestrator as image_orchestrator

    core_db.AsyncSessionLocal = session_factory
    chat_service.AsyncSessionLocal = session_factory
    image_service.AsyncSessionLocal = session_factory
    image_orchestrator.AsyncSessionLocal = session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_factory(client: AsyncClient):
    async def _create(email: str | None = None, password: str = "password123") -> dict:
        email = email or f"user_{uuid.uuid4().hex[:8]}@example.com"
        resp = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test"}
        )
        assert resp.status_code == 201, resp.text
        tokens = resp.json()
        return {
            "email": email,
            "password": password,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
        }

    return _create
