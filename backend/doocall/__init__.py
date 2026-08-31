"""doocall Django project.

Ensure the Celery app is loaded when Django starts so that shared_task
uses this app.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
