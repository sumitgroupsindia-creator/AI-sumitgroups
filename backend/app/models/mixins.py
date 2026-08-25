import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

# Microsecond precision: plain MySQL DATETIME truncates to whole seconds, which makes rows created
# in the same second tie and scrambles created_at ordering (chat messages, subscriptions, results).
PreciseDateTime = DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def _utcnow() -> datetime:
    # Naive UTC: MySQL DATETIME carries no timezone, and the server runs at +00:00.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UUIDPKMixin:
    # SQLAlchemy's generic Uuid type stores as CHAR(32) on MySQL and native UUID elsewhere,
    # so the same models work if the database is ever moved off MySQL.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    # Client-side defaults matter on MySQL: without them these server-default columns stay expired
    # after INSERT (no RETURNING support) and trigger a lazy DB load during response serialization,
    # which is outside SQLAlchemy's async greenlet context and raises MissingGreenlet.
    created_at: Mapped[datetime] = mapped_column(
        PreciseDateTime, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        PreciseDateTime,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        nullable=False,
    )
