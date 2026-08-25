from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("error_handler")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "request_id": request_id_ctx.get()},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "Invalid request", "details": exc.errors(), "request_id": request_id_ctx.get()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = request_id_ctx.get()
        logger.error("http.unhandled_exception", error=str(exc), path=request.url.path, request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"error": "An unexpected error occurred. Please try again.", "request_id": request_id},
        )
