"""Celery app — worker + beat for scheduled background tasks.

Run locally:
    celery -A app.worker.celery_app worker --loglevel=info
    celery -A app.worker.celery_app beat   --loglevel=info

In docker-compose, two dedicated services use these commands (see compose file).
Both share the same Redis instance as broker + result backend.
"""
from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "tchoucti",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.reminders"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Africa/Douala",
    enable_utc=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Periodic schedule: scan due reminders every 15 minutes.
celery_app.conf.beat_schedule = {
    "dispatch-meeting-reminders": {
        "task": "app.tasks.reminders.dispatch_meeting_reminders",
        "schedule": crontab(minute="*/15"),
    },
}
