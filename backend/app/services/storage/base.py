from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def save(self, subdir: str, filename: str, data: bytes) -> str:
        """Persist bytes under subdir/filename, return a storage-relative path."""

    @abstractmethod
    async def read(self, subdir: str, filename: str) -> bytes:
        """Read bytes back. Must raise FileNotFoundError if missing."""

    @abstractmethod
    async def delete(self, subdir: str, filename: str) -> None: ...

    @abstractmethod
    def resolve_path(self, subdir: str, filename: str) -> str:
        """Return an absolute filesystem path for direct streaming (e.g. FileResponse)."""
