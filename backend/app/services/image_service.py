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
    ProviderConfig,
    UploadedFile,
)
from app.providers.base import ImageResult, ProviderError
from app.providers.registry import get_image_provider
from app.services.credit_service import record_usage, refund_credits, reserve_credits
from app.services.storage.base import StorageProvider
from app.utils.image_processing import get_dimensions, make_thumbnail

logger = get_logger("image_service")

_DEFAULT_MODELS = {"openai": "gpt-image-1", "gemini": "gemini-2.5-flash-image"}


async def get_credit_costs(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(ProviderConfig).where(ProviderConfig.capability == "image"))
    return {row.provider: row.credit_cost for row in result.scalars().all()}


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

    costs = await get_credit_costs(db)
    total_needed = {"chat": 0, "image": sum(costs.get(p, 10) for p in providers)}

    reserved: list[tuple[str, int]] = []
    try:
        for provider in providers:
            cost = costs.get(provider, 10)
            await reserve_credits(db, user_id, "image", cost)
            reserved.append((provider, cost))
    except Exception:
        for provider, cost in reserved:
            await refund_credits(db, user_id, "image", cost)
        raise

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
                model=_DEFAULT_MODELS.get(provider, provider),
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
    credit_cost: int,
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
            credit_cost=credit_cost,
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
    credit_cost: int,
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
            prompt=prompt, model=model, input_image=input_image, input_mime=input_mime
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
            credits_consumed=credit_cost,
            status="success",
            latency_ms=latency_ms,
        )
        await db.commit()
    except ProviderError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        result_row.status = "failed"
        result_row.error = "The provider failed to generate an image. You can retry."
        result_row.latency_ms = latency_ms
        await refund_credits(db, user_id, "image", credit_cost)
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
        await refund_credits(db, user_id, "image", credit_cost)
        await db.commit()
        logger.error("image.unexpected_failure", provider=provider_name, error=str(exc), request_ref=request_ref)
