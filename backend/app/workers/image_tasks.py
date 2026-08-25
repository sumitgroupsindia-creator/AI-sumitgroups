import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.image_orchestrator import run_generation
from app.workers.celery_app import celery_app

configure_logging(get_settings().log_level)
logger = get_logger("worker.image_tasks")


@celery_app.task(name="images.run_generation", bind=True, max_retries=0)
def run_generation_task(self, request_id: str, only_provider: str | None = None) -> None:
    logger.info("worker.run_generation.start", request_id=request_id, provider=only_provider)
    try:
        asyncio.run(run_generation(UUID(request_id), only_provider))
    except Exception as exc:
        logger.error("worker.run_generation.failed", request_id=request_id, error=str(exc))
        raise
    logger.info("worker.run_generation.done", request_id=request_id)
