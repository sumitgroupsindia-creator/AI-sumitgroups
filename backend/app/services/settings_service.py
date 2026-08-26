"""Runtime configuration an administrator can change without a deploy.

Values resolve database-first and fall back to the `.env` entry of the same name, so an untouched
deployment behaves exactly as it did before this module existed: a key only becomes database-managed
once someone actually saves it.

Only keys in `CATALOG` are settable. Everything the application needs in order to *reach* the
database in the first place — DATABASE_URL, REDIS_URL, JWT_SECRET, ENVIRONMENT — is deliberately
absent, because a value the app must read before it can query anything cannot live in a query.

Reads come from a short-lived process cache. Backend and worker are separate processes holding
separate caches, so a saved change is visible everywhere within CACHE_TTL_SECONDS rather than
instantly; the window is short enough that an admin sees the effect while still on the page, and
long enough that per-request reads cost nothing.
"""

import time
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt, mask
from app.core.logging import get_logger
from app.models.settings import AppSetting, AppSettingAudit

logger = get_logger("settings")

Kind = Literal["string", "int", "bool", "secret", "select"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    group: str
    kind: Kind
    help: str = ""
    options: tuple[str, ...] = field(default=())

    @property
    def is_secret(self) -> bool:
        return self.kind == "secret"


# Model identifiers are absent on purpose: those live on `provider_configs` and are edited on the
# Models screen. Listing them here too would create a second, silently-ignored place to set them.
CATALOG: tuple[SettingSpec, ...] = (
    SettingSpec(
        "openai_api_key", "OpenAI API key", "AI providers", "secret",
        "Powers whichever slot is backed by OpenAI. Image generation additionally requires a "
        "verified OpenAI organisation.",
    ),
    SettingSpec(
        "gemini_api_key", "Gemini API key", "AI providers", "secret",
        "Powers whichever slot is backed by Google Gemini.",
    ),
    SettingSpec(
        "razorpay_key_id", "Razorpay key ID", "Payments", "string",
        "Starts with rzp_test_ while testing and rzp_live_ once you go live.",
    ),
    SettingSpec("razorpay_key_secret", "Razorpay key secret", "Payments", "secret"),
    SettingSpec(
        "razorpay_webhook_secret", "Razorpay webhook secret", "Payments", "secret",
        "Must match the secret configured on the webhook in the Razorpay dashboard, or every "
        "subscription callback is rejected.",
    ),
    SettingSpec(
        "email_backend", "Delivery method", "Email", "select",
        "console only writes mail to the logs — password reset will not reach anyone until this is smtp.",
        options=("console", "smtp"),
    ),
    SettingSpec("smtp_host", "SMTP host", "Email", "string"),
    SettingSpec("smtp_port", "SMTP port", "Email", "int"),
    SettingSpec("smtp_user", "SMTP username", "Email", "string"),
    SettingSpec("smtp_password", "SMTP password", "Email", "secret"),
    SettingSpec("smtp_from", "From address", "Email", "string"),
    SettingSpec(
        "image_aspect", "Image shape", "Images", "select",
        "Portrait is a phone-shaped 9:16, for stories and status posts. Wording is sent to every "
        "model; OpenAI additionally receives it as a real size, Gemini only as an instruction.",
        options=("portrait", "square", "landscape"),
    ),
    SettingSpec(
        "max_upload_mb", "Max upload size (MB)", "Uploads", "int",
        "The reverse proxy caps request bodies at 25MB, so values above that are rejected before "
        "they ever reach the application.",
    ),
    SettingSpec("max_image_dimension", "Max image dimension (px)", "Uploads", "int"),
    SettingSpec(
        "allowed_upload_extensions", "Allowed extensions", "Uploads", "string",
        "Comma separated, without dots — for example: jpg,jpeg,png,webp",
    ),
    SettingSpec("rate_limit_enabled", "Rate limiting on", "Rate limiting", "bool"),
    SettingSpec("rate_limit_per_minute", "Requests per minute", "Rate limiting", "int"),
    SettingSpec(
        "auth_rate_limit_per_minute", "Auth requests per minute", "Rate limiting", "int",
        "Applies to login, signup and password reset. Keep it well below the general limit.",
    ),
)

CATALOG_BY_KEY: dict[str, SettingSpec] = {spec.key: spec for spec in CATALOG}

CACHE_TTL_SECONDS = 15

_cache: dict[str, str] = {}
_cache_expires_at: float = 0.0
_engine = None
_session_factory: async_sessionmaker | None = None


def _sessions() -> async_sessionmaker:
    """A dedicated, unpooled connection for reading settings.

    Unpooled because the cache means this runs roughly once per TTL per process — a handful of
    connections a minute, far too few to justify holding one open. It also keeps settings reads off
    the request pool, so a connection opened during one event loop is never handed to another.
    """
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        _session_factory = async_sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _session_factory


def _env_defaults() -> dict[str, str]:
    env = get_settings()
    out: dict[str, str] = {}
    for spec in CATALOG:
        raw = getattr(env, spec.key, None)
        # str() rather than `raw or ""`: False and 0 are meaningful values, not absences.
        out[spec.key] = "" if raw is None else str(raw)
    return out


async def _resolved() -> dict[str, str]:
    global _cache, _cache_expires_at
    now = time.monotonic()
    if _cache and now < _cache_expires_at:
        return _cache

    values = _env_defaults()
    async with _sessions()() as session:
        rows = (await session.execute(select(AppSetting))).scalars().all()

    for row in rows:
        spec = CATALOG_BY_KEY.get(row.key)
        if spec is None:
            continue  # a key retired from the catalog; the row is inert
        stored = decrypt(row.value) if row.is_secret else row.value
        if stored is None:
            # Sealed under a key we no longer hold. Falling back to .env beats failing every request;
            # the admin API flags it so it can be re-entered.
            logger.warning("settings.undecryptable", key=row.key)
            continue
        values[row.key] = stored

    _cache = values
    _cache_expires_at = now + CACHE_TTL_SECONDS
    return values


def invalidate() -> None:
    """Drop this process's cache. Other processes still expire on their own TTL.

    The dict is emptied, not merely expired: synchronous readers do not consult the expiry, so
    leaving the old values in place would let them serve configuration that has already been
    replaced.
    """
    global _cache, _cache_expires_at
    _cache = {}
    _cache_expires_at = 0.0


async def reload() -> dict[str, str]:
    invalidate()
    return await _resolved()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def get_str(key: str) -> str:
    return (await _resolved()).get(key, "")


async def get_int(key: str, default: int = 0) -> int:
    raw = (await _resolved()).get(key, "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


async def get_bool(key: str) -> bool:
    return _as_bool((await _resolved()).get(key, ""))


def _sync_values() -> dict[str, str]:
    """Values for the few call paths that are not async — SMTP delivery, webhook signature checks.

    These read whatever the last async refresh left behind, and fall back to `.env` while the cache
    is still cold. A sync caller can therefore be one TTL behind; that is acceptable for the paths
    that use it, and the alternative — turning the whole email and webhook stack async — buys
    nothing. `warm()` is called at startup so the cold window is effectively just process boot.
    """
    return _cache if _cache else _env_defaults()


def get_str_sync(key: str) -> str:
    return _sync_values().get(key, "")


def get_int_sync(key: str, default: int = 0) -> int:
    try:
        return int(_sync_values().get(key, ""))
    except (TypeError, ValueError):
        return default


def get_bool_sync(key: str) -> bool:
    return _as_bool(_sync_values().get(key, ""))


async def warm() -> None:
    """Populate the cache at startup so sync readers are not left on `.env` defaults."""
    await _resolved()


async def get_csv(key: str) -> list[str]:
    raw = await get_str(key)
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


async def snapshot_for_admin(db: AsyncSession) -> list[dict]:
    """Every catalog entry with its effective value — secrets masked, never returned in the clear."""
    values = await _resolved()
    rows = {r.key: r for r in (await db.execute(select(AppSetting))).scalars().all()}

    out: list[dict] = []
    for spec in CATALOG:
        row = rows.get(spec.key)
        effective = values.get(spec.key, "")
        unreadable = bool(row and row.is_secret and decrypt(row.value) is None)
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "group": spec.group,
                "kind": spec.kind,
                "help": spec.help,
                "options": list(spec.options),
                "value": "" if spec.is_secret else effective,
                "masked": mask(effective) if spec.is_secret else "",
                "is_secret": spec.is_secret,
                "is_set": bool(effective),
                "source": "database" if row is not None else "environment",
                "unreadable": unreadable,
            }
        )
    return out


async def apply_changes(
    db: AsyncSession, changes: dict[str, str], actor_id: UUID | None, actor_email: str
) -> list[str]:
    """Persist changes and record who made them. Returns the keys that actually changed."""
    known = {k: v for k, v in changes.items() if k in CATALOG_BY_KEY}
    if not known:
        return []

    before = await _resolved()
    rows = {r.key: r for r in (await db.execute(select(AppSetting))).scalars().all()}
    changed: list[str] = []

    for key, new_value in known.items():
        spec = CATALOG_BY_KEY[key]
        new_value = new_value.strip() if isinstance(new_value, str) else str(new_value)

        # An empty submission for a secret means "leave it alone", not "erase it" — the UI cannot
        # show the current value, so a blank field is the normal state of an untouched form.
        if spec.is_secret and not new_value:
            continue
        if before.get(key, "") == new_value:
            continue

        stored = encrypt(new_value) if spec.is_secret else new_value
        row = rows.get(key)
        if row is None:
            db.add(AppSetting(key=key, value=stored, is_secret=spec.is_secret))
        else:
            row.value = stored
            row.is_secret = spec.is_secret

        db.add(
            AppSettingAudit(
                key=key,
                actor_id=actor_id,
                actor_email=actor_email,
                old_preview=mask(before.get(key, "")) if spec.is_secret else before.get(key, "")[:255],
                new_preview=mask(new_value) if spec.is_secret else new_value[:255],
            )
        )
        changed.append(key)

    if changed:
        await db.commit()
        # Reload rather than merely invalidate: synchronous readers fall back to .env on an empty
        # cache, which would briefly undo the change that was just saved.
        await reload()
        logger.info("settings.updated", keys=changed, actor=actor_email)
    return changed
