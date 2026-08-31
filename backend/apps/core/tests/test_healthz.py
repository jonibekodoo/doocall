"""Smoke test: the Django app boots and serves the liveness probe."""

from __future__ import annotations

from django.test import Client
from django.urls import reverse


def test_healthz_returns_ok() -> None:
    client = Client()
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "doocall-backend"}
