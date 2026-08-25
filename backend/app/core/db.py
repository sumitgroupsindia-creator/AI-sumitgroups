from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
