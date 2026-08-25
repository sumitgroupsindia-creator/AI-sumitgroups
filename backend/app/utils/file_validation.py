import io

from fastapi import UploadFile
from PIL import Image

from app.core.config import get_settings

settings = get_settings()

_MIME_TO_EXT = {
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/webp": {"webp"},
}


class FileValidationError(Exception):
    pass


async def validate_image_upload(file: UploadFile) -> tuple[bytes, str, int, int]:
    """Reads, sniffs, and validates an uploaded image. Returns (bytes, mime_type, width, height).
    Never trusts the client-supplied filename or Content-Type header for anything beyond a hint."""
    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise FileValidationError("Empty file")
    if len(data) > max_bytes:
        raise FileValidationError(f"File exceeds {settings.max_upload_mb}MB limit")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in settings.allowed_extensions_list:
        raise FileValidationError(f"Extension .{ext} is not allowed")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            detected_format = (img.format or "").lower()
    except Exception as exc:
        raise FileValidationError("File is not a valid image") from exc

    detected_mime = {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(detected_format)
    if detected_mime is None or ext not in _MIME_TO_EXT.get(detected_mime, set()):
        raise FileValidationError("File content does not match its extension")

    if width > settings.max_image_dimension or height > settings.max_image_dimension:
        raise FileValidationError(f"Image dimensions exceed {settings.max_image_dimension}px")

    return data, detected_mime, width, height


def re_encode_image(data: bytes, mime_type: str) -> bytes:
    """Re-encodes the image to strip EXIF/metadata and any non-image payload before persisting."""
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime_type]
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB") if fmt == "JPEG" else img
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()
