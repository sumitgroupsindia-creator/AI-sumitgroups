import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import IdempotencyKey


async def get_cached_response(db: AsyncSession, user_id: UUID, key: str) -> tuple[int, dict] | None:
    result = await db.execute(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None or row.response_body is None:
        return None
    return row.status_code or 200, json.loads(row.response_body)


async def store_response(db: AsyncSession, user_id: UUID, key: str, status_code: int, body: dict) -> None:
    db.add(
        IdempotencyKey(
            user_id=user_id, key=key, status_code=status_code, response_body=json.dumps(body, default=str)
        )
    )
    await db.flush()
