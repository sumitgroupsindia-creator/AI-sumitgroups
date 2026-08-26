import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.image import GenerationRequest, GenerationResult, UploadedFile
from app.providers.base import ChatImage
from app.services import pricing_service, prompt_service
from app.services.image_service import get_image_prices, run_single_provider
from app.services.storage.local_storage import get_storage_provider

logger = get_logger("image_orchestrator")


async def run_generation(request_id: UUID, only_provider: str | None = None) -> None:
    """Fires all pending GenerationResult rows for a request concurrently, one independent DB
    session + task per provider, via asyncio.gather(..., return_exceptions=True). This is the crux
    of the 'OpenAI + Gemini concurrently' requirement — providers never block each other."""
    storage = get_storage_provider()

    async with AsyncSessionLocal() as db:
        gen_request = (
            await db.execute(select(GenerationRequest).where(GenerationRequest.id == request_id))
        ).scalar_one_or_none()
        if gen_request is None:
            logger.error("image_orchestrator.request_not_found", request_id=str(request_id))
            return

        results_query = select(GenerationResult).where(GenerationResult.request_id == request_id)
        if only_provider:
            results_query = results_query.where(GenerationResult.provider == only_provider)
        results = (await db.execute(results_query)).scalars().all()

        input_image_bytes: bytes | None = None
        input_mime: str | None = None
        if gen_request.upload_file_id is not None:
            uploaded = (
                await db.execute(select(UploadedFile).where(UploadedFile.id == gen_request.upload_file_id))
            ).scalar_one_or_none()
            if uploaded is not None:
                input_image_bytes = await storage.read("images/uploaded", uploaded.stored_filename)
                input_mime = uploaded.content_type

        prices = await get_image_prices(db)
        user_id = gen_request.user_id
        request_ref = gen_request.request_ref

        pending = [(r.id, r.provider, r.model) for r in results if r.status == "pending"]

        # The house style, the task and the shape are worked out once for the request and shared by
        # both slots: they are answering the same brief, and paying to route it twice would buy the
        # same answer twice. `pending[0]` names the slot whose chat model does that thinking.
        if pending:
            lead_provider = pending[0][1]

            # A photo is read before anything is drawn from it, so the image model is told in words
            # what it is looking at — otherwise it tends to replace the customer's actual product
            # with a generic stand-in.
            vision_brief: str | None = None
            if input_image_bytes is not None:
                vision_brief = await prompt_service.read_attachment(
                    db,
                    ChatImage(data=input_image_bytes, mime_type=input_mime or "image/png"),
                    user_id=user_id,
                    request_id=request_ref,
                    provider=lead_provider,
                )

            aspect = await prompt_service.current_aspect()
            composed = await prompt_service.compose_image(
                db,
                gen_request.prompt,
                user_id=user_id,
                request_id=request_ref,
                provider=lead_provider,
                aspect=aspect,
                vision_brief=vision_brief,
            )
            prompt = composed.prompt
        else:
            prompt = gen_request.prompt
            aspect = prompt_service.DEFAULT_ASPECT

    if not pending:
        return

    tasks = [
        run_single_provider(
            result_id=result_id,
            user_id=user_id,
            provider_name=provider,
            model=model,
            prompt=prompt,
            input_image=input_image_bytes,
            input_mime=input_mime,
            aspect=aspect,
            price=prices.get(provider) or pricing_service.fallback(provider, "image"),
            request_ref=request_ref,
            storage=storage,
        )
        for result_id, provider, model in pending
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    async with AsyncSessionLocal() as db:
        results = (
            await db.execute(select(GenerationResult).where(GenerationResult.request_id == request_id))
        ).scalars().all()
        statuses = {r.status for r in results}
        gen_request = (
            await db.execute(select(GenerationRequest).where(GenerationRequest.id == request_id))
        ).scalar_one()
        if statuses == {"completed"}:
            gen_request.status = "completed"
        elif statuses == {"failed"}:
            gen_request.status = "failed"
        else:
            gen_request.status = "partial"
        await db.commit()
