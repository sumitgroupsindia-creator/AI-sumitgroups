"""The first administrator, created from the environment so a fresh deployment can reach its own
admin screens without anyone hand-editing the database."""
import pytest_asyncio
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.billing import Credit
from app.models.user import User
from app.services import bootstrap_service

PASSWORD = "a-long-enough-password"
DOMAIN = "@bootstrap.test"


@pytest_asyncio.fixture
async def email(request, seeded_db):
    """A address of this test's own, cleaned up afterwards.

    The schema is built once for the whole session, so a shared address would let one test's
    account satisfy — or contradict — the next test's assertion about whether one exists.
    """
    address = f"{request.node.name}{DOMAIN}"
    yield address
    await seeded_db.execute(User.__table__.delete().where(User.email.like(f"%{DOMAIN}")))
    await seeded_db.commit()


def _configure(monkeypatch, email, **overrides):
    settings = get_settings()
    values = {"admin_email": email, "admin_password": PASSWORD, "admin_name": "Ops", **overrides}
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value, raising=False)


async def _fetch(db, email):
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def test_creates_an_admin_with_the_configured_credentials(seeded_db, monkeypatch, email):
    _configure(monkeypatch, email)
    await bootstrap_service.ensure_admin_user(seeded_db)

    user = await _fetch(seeded_db, email)
    assert user is not None
    assert user.is_admin and user.is_active
    assert user.full_name == "Ops"
    assert verify_password(PASSWORD, user.hashed_password)

    credit = (await seeded_db.execute(select(Credit).where(Credit.user_id == user.id))).scalar_one()
    assert credit.balance == 10  # the free plan, same as a normal signup


async def test_running_twice_does_not_reset_a_changed_password(seeded_db, monkeypatch, email):
    """An operator who rotates the admin password must not find the old one back after a restart."""
    _configure(monkeypatch, email)
    await bootstrap_service.ensure_admin_user(seeded_db)

    user = await _fetch(seeded_db, email)
    from app.core.security import hash_password

    user.hashed_password = hash_password("rotated-by-the-operator")
    await seeded_db.commit()

    await bootstrap_service.ensure_admin_user(seeded_db)

    seeded_db.expire_all()
    user = await _fetch(seeded_db, email)
    assert verify_password("rotated-by-the-operator", user.hashed_password)
    assert not verify_password(PASSWORD, user.hashed_password)


async def test_restores_admin_rights_if_they_were_removed(seeded_db, monkeypatch, email):
    _configure(monkeypatch, email)
    await bootstrap_service.ensure_admin_user(seeded_db)

    user = await _fetch(seeded_db, email)
    user.is_admin = False
    user.is_active = False
    await seeded_db.commit()

    await bootstrap_service.ensure_admin_user(seeded_db)

    seeded_db.expire_all()
    user = await _fetch(seeded_db, email)
    assert user.is_admin and user.is_active


async def test_does_nothing_without_configuration(seeded_db, monkeypatch, email):
    """No environment, no account — there is deliberately no built-in default credential."""
    _configure(monkeypatch, email, admin_email="", admin_password="")
    await bootstrap_service.ensure_admin_user(seeded_db)
    assert await _fetch(seeded_db, email) is None


async def test_refuses_a_password_too_short_to_be_worth_having(seeded_db, monkeypatch, email):
    _configure(monkeypatch, email, admin_password="abc")
    await bootstrap_service.ensure_admin_user(seeded_db)
    assert await _fetch(seeded_db, email) is None
