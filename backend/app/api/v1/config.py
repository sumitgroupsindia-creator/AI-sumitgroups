from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.image import ProviderConfig
from app.models.settings import ProviderBrand
from app.schemas.config import PublicModelSlot

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/models", response_model=list[PublicModelSlot])
async def public_model_slots(db: AsyncSession = Depends(get_db)):
    """The model slots as customers see them, named by the product rather than by vendor.

    Unauthenticated on purpose: these labels appear on the marketing page as well as inside the app,
    and nothing here is sensitive — no keys, no model identifiers, only branding and credit prices.
    """
    brands = (await db.execute(select(ProviderBrand).order_by(ProviderBrand.sort_order))).scalars().all()
    configs = (await db.execute(select(ProviderConfig))).scalars().all()

    by_provider: dict[str, dict[str, ProviderConfig]] = {}
    for config in configs:
        by_provider.setdefault(config.provider, {})[config.capability] = config

    slots: list[PublicModelSlot] = []
    for brand in brands:
        capabilities = by_provider.get(brand.provider, {})
        chat = capabilities.get("chat")
        image = capabilities.get("image")
        slots.append(
            PublicModelSlot(
                provider=brand.provider,
                slot=brand.slot,
                tier=brand.tier,
                description=brand.description,
                chat_enabled=bool(chat and chat.is_enabled),
                image_enabled=bool(image and image.is_enabled),
                chat_credit_cost=chat.credit_cost if chat else 0,
                image_credit_cost=image.credit_cost if image else 0,
            )
        )
    return slots
