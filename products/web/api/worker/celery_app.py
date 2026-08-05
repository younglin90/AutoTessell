from celery import Celery

from config import settings

_broker = "memory://" if settings.dev_mode else settings.redis_url
_backend = "cache+memory://" if settings.dev_mode else settings.redis_url

celery_app = Celery(
    "tessell",
    broker=_broker,
    backend=_backend,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Hard kill after 10 minutes; soft kill at 9 minutes
    task_time_limit=settings.job_timeout_seconds,
    task_soft_time_limit=settings.job_soft_timeout_seconds,
    worker_concurrency=settings.worker_concurrency,
    # DEV_MODE: run tasks synchronously in-process (no Redis broker needed)
    task_always_eager=settings.dev_mode,
    task_eager_propagates=settings.dev_mode,
)
