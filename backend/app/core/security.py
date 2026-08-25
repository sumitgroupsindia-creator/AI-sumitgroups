from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

TokenType = Literal["access", "refresh"]

# bcrypt has a hard 72-byte input limit; longer passwords are truncated (matches bcrypt's own
# behavior everywhere else and avoids raising on long-but-valid passphrases).
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: UUID, token_type: TokenType, extra_claims: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    if token_type == "access":
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expire = now + timedelta(days=settings.refresh_token_expire_days)

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def create_token_pair(user_id: UUID, is_admin: bool = False) -> tuple[str, str]:
    access = create_token(user_id, "access", {"is_admin": is_admin})
    refresh = create_token(user_id, "refresh")
    return access, refresh
