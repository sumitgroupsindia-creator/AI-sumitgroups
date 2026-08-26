
import os
import uuid
from decimal import Decimal
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

# Must point at a schema dedicated to tests: the suite DROPs and recreates every table.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "mysql+aiomysql://test:test@127.0.0.1:53306/ai_saas_test?charset=utf8mb4"
)


def _database_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?", 1)[0]


# A guard, not a formality. `create_schema` runs `drop_all`, so the cost of this file being pointed
# at the wrong database once is every row in it. Requiring the name to say `test` means an ordinary
# mistake — a copied .env, an exported DATABASE_URL, a tunnel left open to production — stops here
# instead of at the point of no return.
_name = _database_name(TEST_DATABASE_URL)
if "test" not in _name.lower():
    raise RuntimeError(
        f"Refusing to run: TEST_DATABASE_URL points at a database named {_name!r}, which does not "
        "look like a test database. This suite drops every table it finds."
    )

# The application's own DATABASE_URL is forced to the same schema. Overriding the `get_db`
# dependency is not enough on its own: `settings_service` opens an engine of its own straight from
# the settings, and `test_admin_settings` writes through it. Without this line, a .env pointed at
# production means the suite edits production configuration.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.db import Base, get_db_session  # noqa: E402
from app.services import settings_service  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.image import ProviderConfig  # noqa: E402
from app.models.prompt import PromptTemplate  # noqa: E402
from app.services import prompt_service  # noqa: E402
from app.workers import image_tasks  # noqa: E402
from app.models.settings import ProviderBrand  # noqa: E402
from app.models.billing import Plan  # noqa: E402

SYNC_TEST_DATABASE_URL = TEST_DATABASE_URL.replace("mysql+aiomysql://", "mysql+pymysql://")


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Settings are cached for CACHE_TTL_SECONDS, which would otherwise carry one test's override
    into the next. Clearing on both sides keeps each test's configuration its own."""
    settings_service.invalidate()
    yield
    settings_service.invalidate()


class _NoRouting:
    """Answers the router with "0" — no task template matched."""

    async def complete(self, messages, model, system=None, max_tokens=256):
        return "0"


@pytest.fixture(autouse=True)
def queued_generations(monkeypatch):
    """Keep Celery dispatch off the network, and record it instead.

    Handing a task to Celery opens a connection to the broker. The suite has no Redis and should
    not need one: every test that cares what generation *does* drives `image_orchestrator` directly.
    Left unpatched, `.delay` retries a missing broker twenty times and then fails the test — which
    is exactly how these passed on a laptop with Redis running and failed in CI without it.

    Autouse rather than per-test, because per-test is what went wrong: twenty-four tests remembered
    to patch it and six did not. Returns the list of dispatches, for a test that wants to assert one
    happened.
    """
    sent: list[tuple] = []
    monkeypatch.setattr(
        image_tasks.run_generation_task, "delay", lambda *args, **kwargs: sent.append((args, kwargs))
    )
    return sent


@pytest.fixture(autouse=True)
def offline_prompt_helpers(monkeypatch):
    """Keep the router and the photo-reader off the network.

    Both are real model calls made on the way to answering. Left alone they fire on every test in
    the suite — slow, non-deterministic, and against a fake key, so always a 401 after retries. A
    test that cares about routing installs its own provider over this one.
    """
    monkeypatch.setattr(prompt_service, "get_chat_provider", lambda name: _NoRouting())
    yield


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
                Plan(code="free", name="Free", price=0, currency="INR",
                     monthly_credits=10, max_upload_mb=5),
                Plan(code="pro", name="Pro", price=999, currency="INR",
                     monthly_credits=1000, max_upload_mb=10),
            ]
        )
        db_session.add_all(
            [
                # Mirrors the 0005 migration's seed, so a test asserting on a price is asserting
                # on the same numbers a fresh deployment starts with: chat 1 credit, images
                # 5 + 3 margin = 8.
                ProviderConfig(provider="openai", capability="chat", model="gpt-4o-mini",
                               provider_cost_inr=Decimal("0.1000"), credit_cost=1, margin_credits=0,
                               display_name="OpenAI"),
                ProviderConfig(provider="gemini", capability="chat", model="gemini-2.0-flash",
                               provider_cost_inr=Decimal("0.0500"), credit_cost=1, margin_credits=0,
                               display_name="Gemini"),
                ProviderConfig(provider="openai", capability="image", model="gpt-image-1",
                               provider_cost_inr=Decimal("3.7000"), credit_cost=5, margin_credits=3,
                               display_name="OpenAI"),
                ProviderConfig(provider="gemini", capability="image", model="gemini-2.5-flash-image",
                               provider_cost_inr=Decimal("3.5000"), credit_cost=5, margin_credits=3,
                               display_name="Gemini"),
            ]
        )
        # Mirrors the 0003 migration seed; the tests build the schema from metadata, not migrations.
        db_session.add_all(
            [
                ProviderBrand(provider="openai", slot="Model 1", tier="Standard",
                              description="Balanced quality and speed.", sort_order=1),
                ProviderBrand(provider="gemini", slot="Model 2", tier="Premium",
                              description="Alternative interpretation.", sort_order=2),
            ]
        )
        # Mirrors the 0006 seed. The wording is trimmed — what the tests care about is which rows
        # exist and how each kind is treated, not the prose.
        db_session.add_all(
            [
                PromptTemplate(key="chat_base", scope="chat", kind="base", name="Assistant identity",
                               description="Always applied to every chat turn.",
                               content="You are the AI assistant of Sumit Groups.", sort_order=1),
                PromptTemplate(key="image_base", scope="image", kind="base", name="Image house style",
                               description="Always applied to every generated image.",
                               content="Produce a finished, ready-to-post image.", sort_order=2),
                PromptTemplate(key="story", scope="chat", kind="task", name="Story or script",
                               description="The person wants a story or a script.",
                               content="Write the piece itself, not an outline.", sort_order=10),
                PromptTemplate(key="poster", scope="image", kind="task", name="Poster or banner",
                               description="The image is a poster, banner or offer.",
                               content="The headline is the design.", sort_order=12),
                PromptTemplate(key="task_router", scope="chat", kind="tool", name="Task router",
                               description="Picks which task template fits a request.",
                               content="Answer with the number alone.", sort_order=90),
                PromptTemplate(key="image_vision_brief", scope="image", kind="tool",
                               name="Read the attached photo",
                               description="Describes a photo the customer attached.",
                               content="Describe the attached photo in 60 words or fewer.",
                               sort_order=91),
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

    import app.services.settings_service as settings_service_module

    core_db.AsyncSessionLocal = session_factory
    # Settings normally read through their own unpooled engine; point that at the test engine too.
    settings_service_module._session_factory = session_factory
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
