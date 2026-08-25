import io

from PIL import Image

THUMBNAIL_SIZE = (512, 512)


def make_thumbnail(data: bytes, content_type: str) -> bytes:
    fmt = "PNG" if content_type == "image/png" else "JPEG"
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB") if fmt == "JPEG" else img.convert("RGBA")
        img.thumbnail(THUMBNAIL_SIZE)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()


def get_dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        return img.size
