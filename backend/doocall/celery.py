"""Celery application for the doocall project."""

from __future__ import annotations

import os
from typing import Any

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doocall.settings")

app = Celery("doocall")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self: Any) -> None:  # pragma: no cover - trivial worker smoke task
    print(f"Request: {self.request!r}")
