import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Header, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.core.logging import get_logger, new_request_id
from app.models.image import GenerationRequest, GenerationResult, UploadedFile as UploadedFileModel
from app.models.user import User
from app.providers.registry import AVAILABLE_PROVIDERS
from app.schemas.image import (
    GenerateImageRequest,
    GenerationRequestResponse,
    GenerationResultResponse,
    RegenerateRequest,
    UploadedFileResponse,
)
from app.services import image_service
from app.services.credit_service import InsufficientCreditsError
from app.services.storage.local_storage import get_storage_provider
from app.utils.file_validation import FileValidationError, re_encode_image, validate_image_upload
from app.utils.idempotency import get_cached_response, store_response
from app.workers.image_tasks import run_generation_task

router = APIRouter(prefix="/images", tags=["images"])
logger = get_logger("images.api")
settings = get_settings()


def _to_result_response(result: GenerationResult) -> GenerationResultResponse:
    image_url = f"/api/v1/files/generated/{result.generated_image_id}" if result.generated_image_id else None
    thumb_url = f"/api/v1/files/thumbnail/{result.generated_image_id}" if result.generated_image_id else None
    return GenerationResultResponse(
        id=result.id,
        provider=result.provider,
        status=result.status,
        error=result.error,
        image_url=image_url,
        thumbnail_url=thumb_url,
        created_at=result.created_at,
    )


def _to_request_response(gen_request: GenerationRequest) -> GenerationRequestResponse:
    return GenerationRequestResponse(
        id=gen_request.id,
        prompt=gen_request.prompt,
        status=gen_request.status,
        created_at=gen_request.created_at,
        results=[_to_result_response(r) for r in gen_request.results],
    )


def _validate_providers(providers: list[str]) -> list[str]:
    cleaned = [p for p in dict.fromkeys(providers) if p in AVAILABLE_PROVIDERS]
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid providers specified")
    return cleaned


@router.post("/generate", response_model=GenerationRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_images(
    payload: GenerateImageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        cached = await get_cached_response(db, user.id, idempotency_key)
        if cached:
            return cached[1]

    providers = _validate_providers(payload.providers)
    request_ref = new_request_id()

    try:
        gen_request = await image_service.create_generation_request(
            db,
            user_id=user.id,
            prompt=payload.prompt,
            providers=providers,
            upload_file_id=payload.upload_file_id,
            request_ref=request_ref,
        )
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    run_generation_task.delay(str(gen_request.id))

    response = _to_request_response(gen_request)
    if idempotency_key:
        await store_response(db, user.id, idempotency_key, 202, response.model_dump())
        await db.commit()
    return response


@router.post("/generate-with-upload", response_model=GenerationRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_with_upload(
    file: UploadFile,
    prompt: str = Form(...),
    providers: str = Form("openai,gemini"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        data, mime_type, width, height = await validate_image_upload(file)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    clean_bytes = re_encode_image(data, mime_type)
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
    stored_filename = f"{uuid.uuid4()}.{ext}"
    storage = get_storage_provider()
    await storage.save("images/uploaded", stored_filename, clean_bytes)

    uploaded = UploadedFileModel(
        user_id=user.id,
        stored_filename=stored_filename,
        original_filename=file.filename or "upload",
        content_type=mime_type,
        size_bytes=len(clean_bytes),
        width=width,
        height=height,
    )
    db.add(uploaded)
    await db.flush()

    provider_list = _validate_providers([p.strip() for p in providers.split(",") if p.strip()])
    request_ref = new_request_id()

    try:
        gen_request = await image_service.create_generation_request(
            db,
            user_id=user.id,
            prompt=prompt,
            providers=provider_list,
            upload_file_id=uploaded.id,
            request_ref=request_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    run_generation_task.delay(str(gen_request.id))
    return _to_request_response(gen_request)


@router.get("", response_model=list[GenerationRequestResponse])
async def list_generations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    result = await db.execute(
        select(GenerationRequest)
        .where(GenerationRequest.user_id == user.id)
        .order_by(GenerationRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    requests = result.scalars().all()
    for r in requests:
        await db.refresh(r, attribute_names=["results"])
    return [_to_request_response(r) for r in requests]


@router.get("/{generation_id}", response_model=GenerationRequestResponse)
async def get_generation(
    generation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(GenerationRequest).where(GenerationRequest.id == generation_id, GenerationRequest.user_id == user.id)
    )
    gen_request = result.scalar_one_or_none()
    if gen_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    await db.refresh(gen_request, attribute_names=["results"])
    return _to_request_response(gen_request)


@router.post("/{generation_id}/regenerate", response_model=GenerationRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def regenerate(
    generation_id: UUID,
    payload: RegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GenerationRequest).where(GenerationRequest.id == generation_id, GenerationRequest.user_id == user.id)
    )
    gen_request = result.scalar_one_or_none()
    if gen_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")

    await db.refresh(gen_request, attribute_names=["results"])
    providers = [payload.provider] if payload.provider else [r.provider for r in gen_request.results]
    providers = _validate_providers(providers)

    costs = await image_service.get_credit_costs(db)
    new_result_ids = []
    for provider in providers:
        parent = next((r for r in gen_request.results if r.provider == provider), None)
        new_result = GenerationResult(
            request_id=gen_request.id,
            provider=provider,
            model=parent.model if parent else provider,
            status="pending",
            parent_result_id=parent.id if parent else None,
        )
        db.add(new_result)
        await db.flush()
        new_result_ids.append(new_result.id)

    gen_request.status = "processing"
    await db.commit()
    await db.refresh(gen_request, attribute_names=["results"])

    for provider in providers:
        run_generation_task.delay(str(gen_request.id), provider)

    return _to_request_response(gen_request)
