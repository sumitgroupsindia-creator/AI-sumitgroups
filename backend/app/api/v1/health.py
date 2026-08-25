from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    checks = {"database": False, "redis": False}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        await get_redis().ping()
        checks["redis"] = True
    except Exception:
        pass
    ok = all(checks.values())
    return {"status": "ready" if ok else "degraded", "checks": checks}
