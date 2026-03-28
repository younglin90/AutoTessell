from celery import Celery

from config import settings

celery_app = Celery(
    "tessell",
    broker=settings.redis_url,
    backend=settings.redis_url,
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
)
