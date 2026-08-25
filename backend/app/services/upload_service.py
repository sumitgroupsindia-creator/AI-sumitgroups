"""Turning a client's file into a stored, trusted image.

Extracted so chat attachments and image generation share one path: both must sniff the real format
rather than trust the filename, and both must re-encode before anything is written to disk.
"""
import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import UploadedFile
from app.services.storage.local_storage import get_storage_provider
from app.utils.file_validation import re_encode_image, validate_image_upload

_EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

UPLOAD_SUBDIR = "images/uploaded"


async def store_upload(db: AsyncSession, *, user_id: uuid.UUID, file: UploadFile) -> UploadedFile:
    """Validate, strip metadata, persist. Raises FileValidationError on anything untrusted.

    The row is flushed but not committed: the caller decides whether the upload survives alongside
    whatever it was uploaded for.
    """
    data, mime_type, width, height = await validate_image_upload(file)

    # Re-encoding drops EXIF and any non-image payload smuggled inside the file.
    clean_bytes = re_encode_image(data, mime_type)
    stored_filename = f"{uuid.uuid4()}.{_EXTENSION[mime_type]}"
    await get_storage_provider().save(UPLOAD_SUBDIR, stored_filename, clean_bytes)

    uploaded = UploadedFile(
        user_id=user_id,
        stored_filename=stored_filename,
        original_filename=file.filename or "upload",
        content_type=mime_type,
        size_bytes=len(clean_bytes),
        width=width,
        height=height,
    )
    db.add(uploaded)
    await db.flush()
    return uploaded
