import os
from celery import Celery

# Redis configuration URL matching our cache service
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "url_shortener_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"]
)

# Celery configurations for production resilience
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # Tasks are acknowledged after execution rather than before
    task_reject_on_worker_lost=True,  # Re-enqueue task if worker dies mid-execution
    # Bug #10 fix: bound retry storm behaviour.
    # Without these, a single failing job triggers infinite immediate retries
    # that exhaust the shared DB connection pool and hang the entire API.
    task_soft_time_limit=30,   # SIGALRM after 30s — task can clean up
    task_time_limit=60,        # SIGKILL after 60s — hard ceiling per task
    worker_max_tasks_per_child=500,  # recycle worker processes to prevent leaks
    # Exponential backoff is already enabled per-task via retry_backoff=True;
    # cap the maximum wait to avoid multi-hour delays on persistent failures.
    task_annotations={
        "*": {"retry_backoff_max": 120}  # cap backoff at 2 minutes for all tasks
    },
)
