from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.billing import Credit, Plan, Subscription
from app.services.payment.base import CheckoutOrder, PaymentProvider, WebhookEvent

logger = get_logger("subscription_service")


class SubscriptionError(Exception):
    pass


async def get_plan_by_code(db: AsyncSession, code: str) -> Plan:
    result = await db.execute(select(Plan).where(Plan.code == code, Plan.is_active == True))  # noqa: E712
    plan = result.scalar_one_or_none()
    if plan is None:
        raise SubscriptionError(f"Unknown or inactive plan: {code}")
    return plan


async def get_current_subscription(db: AsyncSession, user_id: UUID) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    return result.scalars().first()


async def start_checkout(
    db: AsyncSession, payment: PaymentProvider, user_id: UUID, plan_code: str
) -> tuple[Subscription, CheckoutOrder]:
    plan = await get_plan_by_code(db, plan_code)
    if plan.price <= 0:
        raise SubscriptionError("This plan does not require checkout")

    subscription = Subscription(user_id=user_id, plan_id=plan.id, status="pending", provider=payment.name)
    db.add(subscription)
    await db.flush()

    amount_minor_units = int(plan.price * 100)
    order = await payment.create_order(amount_minor_units, plan.currency, receipt=str(subscription.id))
    subscription.provider_subscription_id = order.order_id
    await db.commit()
    return subscription, order


async def activate_subscription(db: AsyncSession, provider_subscription_id: str) -> None:
    result = await db.execute(
        select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        logger.error("subscription.activate.not_found", provider_subscription_id=provider_subscription_id)
        return

    plan = (await db.execute(select(Plan).where(Plan.id == subscription.plan_id))).scalar_one()
    now = datetime.now(timezone.utc)
    period_days = 365 if plan.billing_interval == "year" else 30

    subscription.status = "active"
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=period_days)

    credit = (await db.execute(select(Credit).where(Credit.user_id == subscription.user_id).with_for_update())).scalar_one_or_none()
    if credit is None:
        credit = Credit(user_id=subscription.user_id)
        db.add(credit)
    credit.balance = plan.monthly_credits

    await db.commit()


async def renew_subscription(db: AsyncSession, provider_subscription_id: str) -> None:
    await activate_subscription(db, provider_subscription_id)


async def cancel_subscription(db: AsyncSession, user_id: UUID, payment: PaymentProvider) -> Subscription:
    subscription = await get_current_subscription(db, user_id)
    if subscription is None or subscription.status != "active":
        raise SubscriptionError("No active subscription to cancel")

    if subscription.provider_subscription_id and subscription.provider != "none":
        await payment.cancel_subscription(subscription.provider_subscription_id)

    subscription.cancel_at_period_end = True
    subscription.cancelled_at = datetime.now(timezone.utc)
    await db.commit()
    return subscription


async def mark_expired(db: AsyncSession, provider_subscription_id: str) -> None:
    result = await db.execute(
        select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return
    subscription.status = "expired"
    await db.commit()


async def handle_webhook_event(db: AsyncSession, event: WebhookEvent) -> None:
    logger.info("subscription.webhook", event_type=event.event_type)
    if event.event_type in ("subscription.activated", "subscription.charged", "payment.captured"):
        if event.provider_subscription_id:
            await activate_subscription(db, event.provider_subscription_id)
    elif event.event_type == "subscription.cancelled":
        if event.provider_subscription_id:
            await mark_expired(db, event.provider_subscription_id)
    elif event.event_type in ("subscription.completed", "subscription.halted"):
        if event.provider_subscription_id:
            await mark_expired(db, event.provider_subscription_id)
