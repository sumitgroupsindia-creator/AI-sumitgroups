"""Sealing for admin-managed secrets that live in the database.

Provider API keys move out of `.env` and into `app_settings` so they can be rotated from the admin
UI without an SSH session. Storing them in plain text would mean a single database dump hands over
every provider account, so values the catalog marks as secret are sealed with Fernet
(AES-128-CBC + HMAC) before they are written.

The sealing key deliberately never lives in the database. It comes from `SETTINGS_ENCRYPTION_KEY`,
falling back to `JWT_SECRET` so an existing deployment keeps working without a new variable. That
fallback has a consequence worth stating plainly: rotating `JWT_SECRET` also orphans every stored
secret. `decrypt` returns None instead of raising in that case, and the admin API reports the value
as unreadable so an administrator can simply enter it again.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# Marks a value as sealed. Rows written before a key was ever configured, and non-secret rows, are
# stored verbatim — the prefix is what tells the two apart on read.
_PREFIX = "fernet:"


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    material = settings.settings_encryption_key or settings.jwt_secret
    # Fernet requires exactly 32 url-safe base64 bytes; SHA-256 turns any passphrase into that.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(stored: str) -> str | None:
    """Plain text for a sealed value, or None when it cannot be opened with the current key."""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(_PREFIX) :].encode()).decode()
    except InvalidToken:
        return None


def mask(value: str) -> str:
    """A secret rendered for display: enough to recognise which key is set, not enough to use it."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * 8
    return f"{'•' * 8}{value[-4:]}"
