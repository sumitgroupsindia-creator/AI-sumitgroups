from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.models.billing import Plan
from app.models.user import User
from app.schemas.billing import CheckoutRequest, CheckoutResponse, PlanResponse, SubscriptionResponse
from app.services import subscription_service
from app.services.payment.base import PaymentProvider
from app.services.payment.razorpay_provider import get_payment_provider

router = APIRouter(prefix="/subscription", tags=["subscription"])
logger = get_logger("subscription.api")


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.is_active == True).order_by(Plan.price))  # noqa: E712
    return result.scalars().all()


@router.get("", response_model=SubscriptionResponse | None)
async def get_subscription(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    subscription = await subscription_service.get_current_subscription(db, user.id)
    if subscription is None:
        return None
    await db.refresh(subscription, attribute_names=["plan"])
    return subscription


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    payment: PaymentProvider = Depends(get_payment_provider),
):
    try:
        subscription, order = await subscription_service.start_checkout(db, payment, user.id, payload.plan_code)
    except subscription_service.SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CheckoutResponse(
        provider=payment.name,
        order_id=order.order_id,
        amount=order.amount_minor_units,
        currency=order.currency,
        key_id=order.key_id,
        subscription_id=subscription.id,
    )


@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    payment: PaymentProvider = Depends(get_payment_provider),
):
    try:
        subscription = await subscription_service.cancel_subscription(db, user.id, payment)
    except subscription_service.SubscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.refresh(subscription, attribute_names=["plan"])
    return subscription


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payment: PaymentProvider = Depends(get_payment_provider),
):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not payment.verify_webhook_signature(raw_body, signature):
        logger.warning("subscription.webhook.invalid_signature")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    payload = await request.json()
    event = payment.parse_webhook(payload)
    await subscription_service.handle_webhook_event(db, event)
    return {"status": "processed"}
