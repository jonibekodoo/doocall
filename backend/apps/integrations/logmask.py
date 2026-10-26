"""Mask secret path tokens in our own log records.

``/api/public/bitrix24/click-to-call/<token>`` and
``/api/public/kotib/analysis/<token>`` carry a bearer-like secret in the
path. Django logs the path of every 4xx/5xx response ("Unauthorized: …"
via ``django.request``; ``django.server`` in runserver) — this filter
rewrites those records to ``…/<first 4 chars>***``.
"""

from __future__ import annotations

import logging
import re

SECRET_PATH = re.compile(r"(/api/public/(?:bitrix24/click-to-call|kotib/analysis)/)([^/\s?\"'#]+)")
LOGGERS = ("django.request", "django.server", "django.channels.server", "uvicorn.access")


def mask(text: str) -> str:
    return SECRET_PATH.sub(lambda m: f"{m.group(1)}{m.group(2)[:4]}***", text)


class SecretPathFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        masked = mask(message)
        if masked != message:
            record.msg, record.args = masked, ()
        request = getattr(record, "request", None)
        if request is not None and hasattr(request, "path"):
            # Handlers that render the request (e.g. AdminEmailHandler).
            record.request_path = mask(str(request.path))
        return True


def install() -> None:
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, SecretPathFilter) for f in logger.filters):
            logger.addFilter(SecretPathFilter())
