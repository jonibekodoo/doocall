"""Core views — PHASE 1 exposes only a liveness probe.

``/healthz/`` is intentionally dependency-free: it must answer 200 as soon as
the Django process can serve a request, so container orchestrators can tell
"process up" apart from "dependencies wired" (the latter is what the
``check_services`` management command is for).
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness probe. Always cheap, never touches the DB/cache."""
    return JsonResponse({"status": "ok", "service": "doocall-backend"})
