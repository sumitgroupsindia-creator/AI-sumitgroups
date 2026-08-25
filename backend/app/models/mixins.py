import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    # SQLAlchemy's generic Uuid type stores as CHAR(32) on MySQL and native UUID elsewhere,
    # so the same models work if the database is ever moved off MySQL.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
        nullable=False,
    )
