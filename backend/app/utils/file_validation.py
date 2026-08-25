import io

from fastapi import UploadFile
from PIL import Image

from app.services import settings_service

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
    max_mb = await settings_service.get_int("max_upload_mb", 10)
    if len(data) == 0:
        raise FileValidationError("Empty file")
    if len(data) > max_mb * 1024 * 1024:
        raise FileValidationError(f"File exceeds {max_mb}MB limit")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in await settings_service.get_csv("allowed_upload_extensions"):
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

    max_dimension = await settings_service.get_int("max_image_dimension", 4096)
    if width > max_dimension or height > max_dimension:
        raise FileValidationError(f"Image dimensions exceed {max_dimension}px")

    return data, detected_mime, width, height


def re_encode_image(data: bytes, mime_type: str) -> bytes:
    """Re-encodes the image to strip EXIF/metadata and any non-image payload before persisting."""
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime_type]
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB") if fmt == "JPEG" else img
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()
