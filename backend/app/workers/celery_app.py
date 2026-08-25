from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_saas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.image_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=180,
    task_soft_time_limit=150,
    worker_max_tasks_per_child=100,
)
