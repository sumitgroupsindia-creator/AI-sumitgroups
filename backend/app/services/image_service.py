import time
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.chat import Conversation
from app.models.image import (
    GeneratedImage,
    GenerationRequest,
    GenerationResult,
    UploadedFile,
)
from app.providers.base import Aspect, ImageResult, ProviderError
from app.providers.registry import get_image_provider
from app.services import pricing_service
from app.services.credit_service import record_usage, refund_credits, reserve_credits
from app.services.pricing_service import Price
from app.services.storage.base import StorageProvider
from app.utils.image_processing import get_dimensions, make_thumbnail

logger = get_logger("image_service")

_DEFAULT_MODELS = {"openai": "gpt-image-1", "gemini": "gemini-2.5-flash-image"}


async def get_image_prices(db: AsyncSession) -> dict[str, Price]:
    """Every image slot's economics, keyed by provider. A slot with no row still gets a price, so a
    gap in configuration cannot hand out free generations."""
    return await pricing_service.load(db, "image")


async def create_generation_request(
    db: AsyncSession,
    *,
    user_id: UUID,
    prompt: str,
    providers: list[str],
    upload_file_id: UUID | None,
    request_ref: str,
    conversation_id: UUID | None = None,
) -> GenerationRequest:
    if conversation_id is not None:
        owned = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        if owned.scalar_one_or_none() is None:
            raise ValueError("Conversation not found")
    if upload_file_id is not None:
        result = await db.execute(
            select(UploadedFile).where(UploadedFile.id == upload_file_id, UploadedFile.user_id == user_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError("Upload not found")

    prices = await get_image_prices(db)
    resolved = {p: prices.get(p) or pricing_service.fallback(p, "image") for p in providers}

    # Reserved as one sum: asking both slots is a single action to the customer, so being told up
    # front that it is unaffordable beats paying for one picture and being refused the other.
    await reserve_credits(db, user_id, sum(price.credits for price in resolved.values()))

    gen_request = GenerationRequest(
        user_id=user_id,
        conversation_id=conversation_id,
        prompt=prompt,
        upload_file_id=upload_file_id,
        status="processing",
        request_ref=request_ref,
    )
    db.add(gen_request)
    await db.flush()

    for provider in providers:
        db.add(
            GenerationResult(
                request_id=gen_request.id,
                provider=provider,
                model=resolved[provider].model or _DEFAULT_MODELS.get(provider, provider),
                status="pending",
            )
        )
    await db.commit()
    await db.refresh(gen_request, attribute_names=["results"])
    return gen_request


async def run_single_provider(
    *,
    result_id: UUID,
    user_id: UUID,
    provider_name: str,
    model: str,
    prompt: str,
    input_image: bytes | None,
    input_mime: str | None,
    aspect: Aspect,
    price: Price,
    request_ref: str,
    storage: StorageProvider,
) -> None:
    """Runs one provider's generation and persists the outcome, using its own DB session (an
    AsyncSession must not be shared across concurrently-running coroutines). Designed to be awaited
    concurrently alongside sibling providers via asyncio.gather(..., return_exceptions=True) so one
    slow/failing provider never blocks or hides the other's result."""
    async with AsyncSessionLocal() as db:
        await _run_single_provider(
            db,
            result_id=result_id,
            user_id=user_id,
            provider_name=provider_name,
            model=model,
            prompt=prompt,
            input_image=input_image,
            input_mime=input_mime,
            aspect=aspect,
            price=price,
            request_ref=request_ref,
            storage=storage,
        )


async def _run_single_provider(
    db: AsyncSession,
    *,
    result_id: UUID,
    user_id: UUID,
    provider_name: str,
    model: str,
    prompt: str,
    input_image: bytes | None,
    input_mime: str | None,
    aspect: Aspect,
    price: Price,
    request_ref: str,
    storage: StorageProvider,
) -> None:
    result_row = (await db.execute(select(GenerationResult).where(GenerationResult.id == result_id))).scalar_one()
    result_row.status = "processing"
    await db.commit()

    started = time.perf_counter()
    try:
        provider = get_image_provider(provider_name)
        image_result: ImageResult = await provider.generate_image(
            prompt=prompt,
            model=model,
            input_image=input_image,
            input_mime=input_mime,
            aspect=aspect,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        stored_filename = f"{uuid.uuid4()}.png"
        await storage.save("images/generated", stored_filename, image_result.image_bytes)
        thumb_bytes = make_thumbnail(image_result.image_bytes, image_result.content_type)
        thumb_filename = f"{uuid.uuid4()}.png"
        await storage.save("images/thumbnails", thumb_filename, thumb_bytes)
        width, height = get_dimensions(image_result.image_bytes)

        generated_image = GeneratedImage(
            user_id=user_id,
            stored_filename=stored_filename,
            thumbnail_filename=thumb_filename,
            content_type=image_result.content_type,
            width=width,
            height=height,
            size_bytes=len(image_result.image_bytes),
        )
        db.add(generated_image)
        await db.flush()

        result_row.status = "completed"
        result_row.generated_image_id = generated_image.id
        result_row.latency_ms = latency_ms
        await record_usage(
            db,
            user_id=user_id,
            request_id=request_ref,
            provider=provider_name,
            model=model,
            operation="image_generate",
            credits_consumed=price.credits,
            cost_inr=price.cost_inr,
            status="success",
            latency_ms=latency_ms,
        )
        await db.commit()
    except ProviderError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        result_row.status = "failed"
        result_row.error = "The provider failed to generate an image. You can retry."
        result_row.latency_ms = latency_ms
        await refund_credits(db, user_id, price.credits)
        await record_usage(
            db,
            user_id=user_id,
            request_id=request_ref,
            provider=provider_name,
            model=model,
            operation="image_generate",
            credits_consumed=0,
            status="failed",
            latency_ms=latency_ms,
            error=str(exc),
        )
        await db.commit()
        logger.error("image.provider_failed", provider=provider_name, error=str(exc), request_ref=request_ref)
    except Exception as exc:  # unexpected failure — still must not crash the sibling task
        result_row.status = "failed"
        result_row.error = "Unexpected error while generating the image."
        await refund_credits(db, user_id, price.credits)
        await db.commit()
        logger.error("image.unexpected_failure", provider=provider_name, error=str(exc), request_ref=request_ref)
