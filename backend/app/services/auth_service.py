import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_token_pair, decode_token, hash_password, verify_password
from app.models.billing import Credit, Plan, Subscription
from app.models.user import PasswordReset, User
from app.services.email_service import send_password_reset_email

settings = get_settings()

RESET_TOKEN_TTL = timedelta(hours=1)


class AuthError(Exception):
    pass


async def register_user(db: AsyncSession, email: str, password: str, full_name: str | None) -> User:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise AuthError("An account with this email already exists")

    user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
    db.add(user)
    await db.flush()

    credit = Credit(user_id=user.id, balance=0)
    db.add(credit)

    free_plan = (await db.execute(select(Plan).where(Plan.code == "free"))).scalar_one_or_none()
    if free_plan is not None:
        db.add(
            Subscription(
                user_id=user.id,
                plan_id=free_plan.id,
                status="active",
                provider="none",
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=3650),
            )
        )
        credit.balance = free_plan.monthly_credits

    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password")
    if not user.is_active:
        raise AuthError("Account is disabled")
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    return create_token_pair(user.id, is_admin=user.is_admin)


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise AuthError("Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise AuthError("Invalid refresh token")

    user = (await db.execute(select(User).where(User.id == UUID(payload["sub"])))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("Invalid refresh token")
    return issue_tokens(user)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def request_password_reset(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        return  # do not leak account existence

    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=_hash_token(raw_token)))
    await db.commit()

    reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
    send_password_reset_email(user.email, reset_link)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    token_hash = _hash_token(token)
    result = await db.execute(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
    reset_row = result.scalar_one_or_none()
    if reset_row is None or reset_row.used:
        raise AuthError("Invalid or expired reset token")
    if datetime.now(timezone.utc) - reset_row.created_at.replace(tzinfo=timezone.utc) > RESET_TOKEN_TTL:
        raise AuthError("Invalid or expired reset token")

    user = (await db.execute(select(User).where(User.id == reset_row.user_id))).scalar_one_or_none()
    if user is None:
        raise AuthError("Invalid or expired reset token")

    user.hashed_password = hash_password(new_password)
    reset_row.used = True
    await db.commit()
