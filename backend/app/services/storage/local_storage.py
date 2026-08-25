import os
from functools import lru_cache

import aiofiles

from app.core.config import get_settings
from app.services.storage.base import StorageProvider

settings = get_settings()

_ALLOWED_SUBDIRS = {"images/generated", "images/uploaded", "images/thumbnails", "temp"}


class PathTraversalError(Exception):
    pass


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_path: str | None = None) -> None:
        self._base = os.path.abspath(base_path or settings.storage_path)

    def _safe_path(self, subdir: str, filename: str) -> str:
        if subdir not in _ALLOWED_SUBDIRS:
            raise PathTraversalError(f"Disallowed storage subdir: {subdir}")
        if filename != os.path.basename(filename) or filename in ("", ".", ".."):
            raise PathTraversalError(f"Disallowed filename: {filename}")

        full = os.path.abspath(os.path.join(self._base, subdir, filename))
        root = os.path.abspath(os.path.join(self._base, subdir))
        if os.path.commonpath([full, root]) != root:
            raise PathTraversalError("Resolved path escapes storage root")
        return full

    async def save(self, subdir: str, filename: str, data: bytes) -> str:
        path = self._safe_path(subdir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return os.path.join(subdir, filename)

    async def read(self, subdir: str, filename: str) -> bytes:
        path = self._safe_path(subdir, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, subdir: str, filename: str) -> None:
        path = self._safe_path(subdir, filename)
        if os.path.isfile(path):
            os.remove(path)

    def resolve_path(self, subdir: str, filename: str) -> str:
        return self._safe_path(subdir, filename)


@lru_cache
def get_storage_provider() -> StorageProvider:
    return LocalStorageProvider()
