from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.image import GeneratedImage, UploadedFile
from app.models.user import User
from app.schemas.image import UploadedFileResponse
from app.services import upload_service
from app.services.storage.local_storage import get_storage_provider
from app.utils.file_validation import FileValidationError

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", response_model=UploadedFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Stores an image and returns its id, for attaching to a chat turn or an image generation."""
    try:
        uploaded = await upload_service.store_upload(db, user_id=user.id, file=file)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    await db.refresh(uploaded)
    return uploaded


@router.get("/generated/{image_id}")
async def get_generated_image(
    image_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(GeneratedImage).where(GeneratedImage.id == image_id))
    image = result.scalar_one_or_none()
    if image is None or image.user_id != user.id:
        # 404, not 403 — never reveal whether another user's resource exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    storage = get_storage_provider()
    path = storage.resolve_path("images/generated", image.stored_filename)
    return FileResponse(path, media_type=image.content_type)


@router.get("/thumbnail/{image_id}")
async def get_thumbnail(image_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GeneratedImage).where(GeneratedImage.id == image_id))
    image = result.scalar_one_or_none()
    if image is None or image.user_id != user.id or image.thumbnail_filename is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    storage = get_storage_provider()
    path = storage.resolve_path("images/thumbnails", image.thumbnail_filename)
    return FileResponse(path, media_type=image.content_type)


@router.get("/uploaded/{file_id}")
async def get_uploaded_file(file_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UploadedFile).where(UploadedFile.id == file_id))
    uploaded = result.scalar_one_or_none()
    if uploaded is None or uploaded.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    storage = get_storage_provider()
    path = storage.resolve_path("images/uploaded", uploaded.stored_filename)
    return FileResponse(path, media_type=uploaded.content_type)
