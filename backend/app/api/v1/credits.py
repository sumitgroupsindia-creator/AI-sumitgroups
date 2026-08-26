from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.billing import UsageRecord
from app.models.user import User
from app.schemas.billing import CreditsResponse, UsageRecordResponse
from app.services.credit_service import get_or_create_credits

router = APIRouter(tags=["credits"])


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    credit = await get_or_create_credits(db, user.id)
    await db.commit()
    return CreditsResponse(balance=credit.balance)


@router.get("/usage", response_model=list[UsageRecordResponse])
async def get_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.user_id == user.id)
        .order_by(UsageRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
