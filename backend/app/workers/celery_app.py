from celery import Celery
from celery.signals import worker_ready

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


@worker_ready.connect
def _check_storage(**_kwargs) -> None:
    """The worker is the process that actually writes generated images, so this is the one where an
    unwritable mount matters most. Reported at boot rather than discovered one failed picture at a
    time."""
    from app.services.storage.preflight import check_storage_writable

    try:
        check_storage_writable()
    except Exception:  # a broken probe must not stop the worker consuming tasks
        pass
