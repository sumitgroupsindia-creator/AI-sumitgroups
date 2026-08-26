"""Creates the first administrator, so a fresh deployment is not locked out of its own admin screens.

Driven entirely by `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME` in the environment. Nothing here
carries a default credential: a hard-coded admin password in source is a published admin password,
and every deployment built from this repository would share it.

Idempotent, and deliberately conservative about the password. On the first run it creates the
account; on every run after that it only ensures the account is still an administrator. It will not
reset a password that someone has since changed — an operator who rotates the admin password in the
app should not find the old one restored by the next restart.

Safe to run concurrently. Several workers boot at once and each runs this, so the losers of that
race are expected to hit the unique constraint on the email; they treat it as success, because the
winner created exactly the row they were about to.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.billing import Credit, Plan, Subscription
from app.models.user import User

logger = get_logger("bootstrap")

MIN_PASSWORD_LENGTH = 8


async def ensure_admin_user(db: AsyncSession) -> None:
    settings = get_settings()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""

    if not email or not password:
        return
    if len(password) < MIN_PASSWORD_LENGTH:
        logger.warning("bootstrap.admin_password_too_short", email=email)
        return

    if await _promote_if_present(db, email):
        return

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=settings.admin_name or None,
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Same starting position a normal signup gets, so the admin's own account behaves like a
    # customer's when they use the product rather than administer it.
    credit = Credit(user_id=user.id, balance=0)
    db.add(credit)
    free_plan = (await db.execute(select(Plan).where(Plan.code == "free"))).scalar_one_or_none()
    if free_plan is not None:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        db.add(
            Subscription(
                user_id=user.id,
                plan_id=free_plan.id,
                status="active",
                provider="none",
                current_period_start=now,
                current_period_end=now + timedelta(days=3650),
            )
        )
        credit.balance = free_plan.monthly_credits

    try:
        await db.commit()
    except IntegrityError:
        # Another worker got there first. Its row is the one we wanted, so this is not a failure.
        await db.rollback()
        await _promote_if_present(db, email)
        return
    logger.info("bootstrap.admin_created", email=email)


async def _promote_if_present(db: AsyncSession, email: str) -> bool:
    """Returns whether the account already exists, making sure it can still reach the admin screens
    if someone has since deactivated or demoted it."""
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        return False
    if not user.is_admin or not user.is_active:
        user.is_admin = True
        user.is_active = True
        await db.commit()
        logger.info("bootstrap.admin_restored", email=email)
    return True
