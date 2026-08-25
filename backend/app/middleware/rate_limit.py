import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.deps import get_redis

settings = get_settings()

_AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/forgot-password"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed fixed-window limiter. Per-IP for unauthenticated auth endpoints (brute-force
    protection), per-user (falling back to per-IP) for everything else under /api/v1/."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1/") or path in ("/api/v1/health", "/api/v1/ready"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization", "")
        identity = auth_header[-24:] if auth_header else client_ip

        if path in _AUTH_PATHS:
            limit = settings.auth_rate_limit_per_minute
            key = f"ratelimit:auth:{client_ip}"
        else:
            limit = settings.rate_limit_per_minute
            key = f"ratelimit:api:{identity}"

        window = int(time.time() // 60)
        redis_key = f"{key}:{window}"

        try:
            redis_client = get_redis()
            count = await redis_client.incr(redis_key)
            if count == 1:
                await redis_client.expire(redis_key, 60)
        except Exception:
            # Redis unavailable: fail open rather than taking the whole API down.
            return await call_next(request)

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests, please slow down.", "request_id": request.headers.get("X-Request-Id", "-")},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
