from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_admin_user, get_db
from app.models.billing import Subscription
from app.models.chat import Conversation
from app.models.image import GenerationRequest, GenerationResult, ProviderConfig
from app.models.settings import AppSettingAudit, ProviderBrand
from app.models.user import User
from app.schemas.admin import (
    AdminProviderBrandResponse,
    AdminProviderConfigResponse,
    AdminSettingAuditResponse,
    AdminSettingResponse,
    AdminStatsResponse,
    AdminUpdatePlanRequest,
    AdminUpdateProviderBrandRequest,
    AdminUpdateProviderConfigRequest,
    AdminUpdateSettingsRequest,
    AdminUpdateUserRequest,
    AdminUserResponse,
)
from app.services import settings_service
from app.schemas.billing import PlanResponse
from app.schemas.image import AdminGenerationResultResponse
from app.models.billing import Plan

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_subs = (
        await db.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))
    ).scalar_one()
    total_conversations = (await db.execute(select(func.count(Conversation.id)))).scalar_one()
    total_gen_requests = (await db.execute(select(func.count(GenerationRequest.id)))).scalar_one()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    failed_24h = (
        await db.execute(
            select(func.count(GenerationResult.id)).where(
                GenerationResult.status == "failed", GenerationResult.created_at >= since
            )
        )
    ).scalar_one()
    return AdminStatsResponse(
        total_users=total_users,
        active_subscriptions=active_subs,
        total_conversations=total_conversations,
        total_generation_requests=total_gen_requests,
        failed_generations_last_24h=failed_24h,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    result = await db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
    return result.scalars().all()


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(user_id: UUID, payload: AdminUpdateUserRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/plans", response_model=list[PlanResponse])
async def list_all_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).order_by(Plan.price))
    return result.scalars().all()


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(plan_id: UUID, payload: AdminUpdatePlanRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get("/models", response_model=list[AdminProviderConfigResponse])
async def list_provider_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProviderConfig).order_by(ProviderConfig.provider, ProviderConfig.capability))
    return result.scalars().all()


@router.patch("/models/{config_id}", response_model=AdminProviderConfigResponse)
async def update_provider_config(
    config_id: UUID, payload: AdminUpdateProviderConfigRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ProviderConfig).where(ProviderConfig.id == config_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider config not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/generations/failed", response_model=list[AdminGenerationResultResponse])
async def list_failed_generations(
    db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200), offset: int = Query(0, ge=0)
):
    result = await db.execute(
        select(GenerationResult)
        .where(GenerationResult.status == "failed")
        .order_by(GenerationResult.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    results = result.scalars().all()
    return [
        AdminGenerationResultResponse(
            id=r.id, provider=r.provider, model=r.model, status=r.status, error=r.error,
            image_url=None, thumbnail_url=None, created_at=r.created_at,
        )
        for r in results
    ]


@router.get("/brands", response_model=list[AdminProviderBrandResponse])
async def list_provider_brands(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProviderBrand).order_by(ProviderBrand.sort_order))
    return result.scalars().all()


@router.patch("/brands/{brand_id}", response_model=AdminProviderBrandResponse)
async def update_provider_brand(
    brand_id: UUID, payload: AdminUpdateProviderBrandRequest, db: AsyncSession = Depends(get_db)
):
    """Rename a customer-facing slot — "Model 1", its tier, its blurb.

    Takes effect for every user on their next page load; nothing here touches which provider
    actually serves the slot, which is the Models screen's job.
    """
    result = await db.execute(select(ProviderBrand).where(ProviderBrand.id == brand_id))
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider brand not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    await db.commit()
    await db.refresh(brand)
    return brand


@router.get("/settings", response_model=list[AdminSettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)):
    return await settings_service.snapshot_for_admin(db)


@router.put("/settings", response_model=list[AdminSettingResponse])
async def update_settings(
    payload: AdminUpdateSettingsRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    await settings_service.apply_changes(db, payload.values, actor_id=admin.id, actor_email=admin.email)
    return await settings_service.snapshot_for_admin(db)


@router.get("/settings/audit", response_model=list[AdminSettingAuditResponse])
async def list_setting_audit(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=200)):
    result = await db.execute(
        select(AppSettingAudit).order_by(AppSettingAudit.created_at.desc()).limit(limit)
    )
    return result.scalars().all()
