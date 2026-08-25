from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger, new_request_id, request_id_ctx, user_id_ctx

logger = get_logger("http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or new_request_id()
        request_id_ctx.set(request_id)
        user_id_ctx.set("-")

        import time

        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        response.headers["X-Request-Id"] = request_id
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        return response
