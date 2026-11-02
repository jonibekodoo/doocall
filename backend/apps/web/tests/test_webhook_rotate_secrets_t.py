"""Tester: rotated webhook secret is shown once and never leaks."""

from __future__ import annotations

import json

import pytest
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db
URL = "/api/web/v1/settings/webhook"


def test_rotate_shows_once_and_never_leaks(client: APIClient, company: Company) -> None:
    first = client.post(f"{URL}/rotate-secret").json()
    secret = first["secret"]
    assert len(secret) == 64 and first["success"] is True
    got = client.get(URL)
    assert secret not in got.content.decode()
    assert got.json()["secret_hint"] == secret[-4:]
    for log in AuditLog.objects.all():
        assert secret not in json.dumps(log.changes)
    company.refresh_from_db()
    assert company.webhook_secret == secret
    second = client.post(f"{URL}/rotate-secret").json()["secret"]
    assert second != secret
    company.refresh_from_db()
    assert company.webhook_secret == second


def test_rotate_rate_limit_and_saving_url_keeps_secret(client: APIClient, company: Company) -> None:
    secret = client.post(f"{URL}/rotate-secret").json()["secret"]
    codes = [client.post(f"{URL}/rotate-secret").status_code for _ in range(5)]
    assert codes[-1] == 429
    company.refresh_from_db()
    kept = company.webhook_secret
    put = client.put(URL, {"webhook_url": "https://example.com/hook"}, format="json")
    assert put.status_code == 200
    assert put.json().get("secret") in (None, "")
    company.refresh_from_db()
    assert company.webhook_secret == kept and kept != ""
