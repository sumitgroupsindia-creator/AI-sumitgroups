from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, chat, config, credits, files, health, images, subscription, user
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.core.db import AsyncSessionLocal
from app.services import bootstrap_service, settings_service

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app.startup", environment=settings.environment)
    # Populate the settings cache before the first request, so the handful of synchronous readers
    # (SMTP, webhook signatures) never fall back to .env on a cold process.
    try:
        await settings_service.warm()
    except Exception:  # a settings table that is not migrated yet must not block startup
        logger.warning("settings.warm_failed", exc_info=True)

    try:
        async with AsyncSessionLocal() as db:
            await bootstrap_service.ensure_admin_user(db)
    except Exception:  # never let a bootstrap problem stop the API from serving
        logger.warning("bootstrap.admin_failed", exc_info=True)
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="ai.sumitgroups.com API",
    version="1.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"],
    expose_headers=["X-Request-Id", "X-Conversation-Id"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)

register_error_handlers(app)

app.include_router(health.router)  # bare /health, /ready for infra/LB checks
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(chat.conversations_router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(subscription.router, prefix="/api/v1")
app.include_router(credits.router, prefix="/api/v1")
app.include_router(config.router, prefix="/api/v1")  # public model branding, no auth
app.include_router(admin.router, prefix="/api/v1")
