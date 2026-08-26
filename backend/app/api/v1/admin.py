from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_admin_user, get_db
from app.models.billing import Subscription, UsageRecord
from app.models.chat import Conversation
from app.models.image import GenerationRequest, GenerationResult, ProviderConfig
from app.models.prompt import PromptTemplate
from app.models.settings import AppSettingAudit, ProviderBrand
from app.models.user import User
from app.schemas.admin import (
    AdminPricingResponse,
    AdminPromptTemplateResponse,
    AdminUpdatePromptTemplateRequest,
    AdminPricingRow,
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
from app.services import pricing_service, settings_service
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


def _config_response(config: ProviderConfig) -> AdminProviderConfigResponse:
    """Prices go out with the charge and the profit already worked out, from the same calculation
    the billing path uses — an administrator should never have to add the margin up by eye and get
    a different answer than the wallet does."""
    price = pricing_service.from_config(config)
    return AdminProviderConfigResponse(
        id=config.id,
        provider=config.provider,
        capability=config.capability,
        model=config.model,
        is_enabled=config.is_enabled,
        provider_cost_inr=price.cost_inr,
        credit_cost=price.base_credits,
        margin_credits=price.margin_credits,
        charge_credits=price.credits,
        profit_inr=price.profit_inr,
        display_name=config.display_name,
    )


@router.get("/models", response_model=list[AdminProviderConfigResponse])
async def list_provider_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProviderConfig).order_by(ProviderConfig.provider, ProviderConfig.capability))
    return [_config_response(config) for config in result.scalars().all()]


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
    return _config_response(config)


# Chat is billed per turn and images per picture; the ledger records the narrower operation names,
# so they are folded back to the capability a price is configured against. The `assist_*` rows are
# the product's own helper calls — routing a request to a style, reading an attached photo. They
# earn nothing and are billed to us, which is exactly why they belong in this report.
_CAPABILITY_OF_OPERATION = {
    "chat": "chat",
    "image_generate": "image",
    "image_edit": "image",
    "assist_route": "chat",
    "assist_vision": "chat",
}


@router.get("/pricing", response_model=AdminPricingResponse)
async def get_pricing(db: AsyncSession = Depends(get_db), days: int = Query(30, ge=1, le=365)):
    """Current prices next to what they actually earned.

    Revenue and spend come from `usage_records`, not from recomputing today's prices over past
    operations — repricing a provider tomorrow must not rewrite what last month made. Only
    successful operations count: a failure is refunded, so it earned nothing and, as far as we can
    tell, cost nothing.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    # Operations counts only what was sold, while spend covers everything that ran — a helper call
    # costs money without being a thing the customer asked for, and counting it as one would make
    # the per-operation figures read lower than they are.
    ledger = (
        await db.execute(
            select(
                UsageRecord.provider,
                UsageRecord.operation,
                func.coalesce(func.sum(case((UsageRecord.credits_consumed > 0, 1), else_=0)), 0),
                func.coalesce(func.sum(UsageRecord.credits_consumed), 0),
                func.coalesce(func.sum(UsageRecord.cost_inr), 0),
            )
            .where(UsageRecord.status == "success", UsageRecord.created_at >= since)
            .group_by(UsageRecord.provider, UsageRecord.operation)
        )
    ).all()

    totals: dict[tuple[str, str], tuple[int, Decimal, Decimal]] = {}
    for provider, operation, count, credits, spend in ledger:
        capability = _CAPABILITY_OF_OPERATION.get(operation)
        if capability is None:
            continue
        seen_count, seen_revenue, seen_spend = totals.get((provider, capability), (0, Decimal(0), Decimal(0)))
        totals[(provider, capability)] = (
            seen_count + count,
            seen_revenue + Decimal(credits),
            seen_spend + Decimal(spend),
        )

    configs = (
        await db.execute(select(ProviderConfig).order_by(ProviderConfig.capability, ProviderConfig.provider))
    ).scalars().all()

    rows: list[AdminPricingRow] = []
    for config in configs:
        price = pricing_service.from_config(config)
        operations, revenue, spend = totals.get((config.provider, config.capability), (0, Decimal(0), Decimal(0)))
        rows.append(
            AdminPricingRow(
                provider=config.provider,
                capability=config.capability,
                model=config.model,
                display_name=config.display_name,
                is_enabled=config.is_enabled,
                cost_inr=price.cost_inr,
                base_credits=price.base_credits,
                margin_credits=price.margin_credits,
                charge_credits=price.credits,
                profit_per_op_inr=price.profit_inr,
                operations=operations,
                revenue_inr=revenue,
                spend_inr=spend,
                profit_inr=revenue - spend,
            )
        )

    return AdminPricingResponse(
        days=days,
        rows=rows,
        total_operations=sum(row.operations for row in rows),
        total_revenue_inr=sum((row.revenue_inr for row in rows), Decimal(0)),
        total_spend_inr=sum((row.spend_inr for row in rows), Decimal(0)),
        total_profit_inr=sum((row.profit_inr for row in rows), Decimal(0)),
    )


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


@router.get("/prompts", response_model=list[AdminPromptTemplateResponse])
async def list_prompt_templates(db: AsyncSession = Depends(get_db)):
    """The instructions the product adds to every request. See `app.services.prompt_service`."""
    result = await db.execute(select(PromptTemplate).order_by(PromptTemplate.sort_order))
    return result.scalars().all()


@router.patch("/prompts/{template_id}", response_model=AdminPromptTemplateResponse)
async def update_prompt_template(
    template_id: UUID, payload: AdminUpdatePromptTemplateRequest, db: AsyncSession = Depends(get_db)
):
    """Reword a template, or switch it off.

    `key`, `scope` and `kind` are deliberately not editable: the code looks templates up by key and
    treats each kind differently, so letting those change from a text box would let an administrator
    quietly detach a row from the thing that reads it.
    """
    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


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
