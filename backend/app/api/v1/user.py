from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/user", tags=["user"])


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if payload.full_name is not None:
        user.full_name = payload.full_name
    await db.commit()
    await db.refresh(user)
    return user
