"""Mask secret path tokens in our own log records.

``/api/public/bitrix24/click-to-call/<token>`` and
``/api/public/kotib/analysis/<token>`` carry a bearer-like secret in the
path, and ``/api/public/rec/<id>?sig=<sig>`` a signed-URL secret. Django logs
the path of every 4xx/5xx response ("Unauthorized: …" via ``django.request``;
``django.server`` in runserver) — this filter rewrites those records to
``…/<first 4 chars>***``.

The JSON formatter also serializes every extra record attribute (``str()``
of non-JSON values), so ``record.request`` — whose repr is
``<WSGIRequest: POST '/api/public/kotib/analysis/<token>'>`` — and any other
attribute carrying such a path are masked too. The real request object is
never mutated: the record gets a proxy whose ``str``/``repr`` are masked and
which delegates everything else (e.g. for AdminEmailHandler).
"""

from __future__ import annotations

import logging
import re
from typing import Any

SECRET_PATH = re.compile(r"(/api/public/(?:bitrix24/click-to-call|kotib/analysis)/)([^/\s?\"'#]+)")
SIGNED_REC = re.compile(r"(/api/public/rec/[^?\s\"'#]*\?(?:[^\s\"'#]*?[&;])?sig=)([^&;\s\"'#]+)")
LOGGERS = ("django.request", "django.server", "django.channels.server", "uvicorn.access")
# LogRecord's own attributes; ``msg``/``args`` are handled via getMessage().
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_path"}
_PLAIN = (int, float, bool, type(None))


def mask(text: str) -> str:
    text = SECRET_PATH.sub(lambda m: f"{m.group(1)}{m.group(2)[:4]}***", text)
    return SIGNED_REC.sub(lambda m: f"{m.group(1)}***", text)


class MaskedProxy:
    """Stands in for a log-record attribute: masked ``str``/``repr``, every
    other attribute delegated to the wrapped object (left untouched)."""

    __slots__ = ("_wrapped",)

    def __init__(self, wrapped: Any) -> None:
        object.__setattr__(self, "_wrapped", wrapped)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def __str__(self) -> str:
        return mask(str(self._wrapped))

    def __repr__(self) -> str:
        return mask(repr(self._wrapped))


def _masked_value(value: Any) -> Any:
    """Masked replacement for ``value``, or None when it carries no secret."""
    if isinstance(value, (*_PLAIN, MaskedProxy)):
        return None
    if isinstance(value, str):
        masked = mask(value)
        return masked if masked != value else None
    try:
        text = str(value)
    except Exception:  # noqa: BLE001 - never break logging
        return None
    return MaskedProxy(value) if mask(text) != text else None


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
        if request is not None and not isinstance(request, MaskedProxy):
            if hasattr(request, "path"):
                # Handlers that render the request (e.g. AdminEmailHandler).
                record.request_path = mask(str(request.path))
            record.request = MaskedProxy(request)
        # Everything else the JSON formatter serializes (extra attributes).
        for name, value in list(vars(record).items()):
            if name not in _RESERVED and (new := _masked_value(value)) is not None:
                setattr(record, name, new)
        return True


def install() -> None:
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, SecretPathFilter) for f in logger.filters):
            logger.addFilter(SecretPathFilter())
