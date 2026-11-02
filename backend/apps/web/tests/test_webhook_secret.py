"""Webhook HMAC secret: rotate (shown once), GET masked with a 4-char hint,
admin-only, rate-limited, audited without the secret."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from typing import Any

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.web import tasks as web_tasks

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/webhook"
ROTATE = f"{URL}/rotate-secret"


@pytest.fixture(autouse=True)
def _fresh_throttle() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


def test_rotate_returns_new_secret_once_and_get_stays_masked(
    client: APIClient, company: Company
) -> None:
    client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json")
    company.refresh_from_db()
    first = company.webhook_secret

    response = client.post(ROTATE)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "secret"} and body["success"] is True
    secret = body["secret"]
    assert len(secret) == 64 and int(secret, 16) >= 0 and secret != first
    company.refresh_from_db()
    assert company.webhook_secret == secret

    view = client.get(URL).json()
    assert view["secret_set"] is True and view["secret_hint"] == secret[-4:]
    assert secret not in json.dumps(view)
    # The URL is untouched; re-saving it keeps the rotated secret.
    assert view["webhook_url"] == "https://crm.example.uz/hook"
    resave = client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json").json()
    assert resave["secret"] is None
    company.refresh_from_db()
    assert company.webhook_secret == secret


def test_get_without_secret_has_no_hint(client: APIClient) -> None:
    body = client.get(URL).json()
    assert (body["secret_set"], body["secret_hint"]) == (False, None)


def test_rotate_works_before_url_is_set(client: APIClient, company: Company) -> None:
    secret = client.post(ROTATE).json()["secret"]
    company.refresh_from_db()
    assert company.webhook_secret == secret
    # First URL save no longer generates (a secret already exists).
    assert (
        client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json").json()["secret"]
        is None
    )


def test_test_delivery_is_signed_with_the_rotated_secret(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X-Doocall-Signature = hex HMAC-SHA256(secret, exact raw body) — the
    documented receiver check passes with the secret returned by rotate."""
    client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json")
    secret = client.post(ROTATE).json()["secret"]
    sent: dict[str, Any] = {}

    class _Resp:
        status = 200

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def fake_open(request: Any, timeout: int = 10) -> _Resp:
        sent["body"] = request.data
        sent["sig"] = request.get_header("X-doocall-signature")
        return _Resp()

    monkeypatch.setattr(web_tasks.netguard, "open_url", fake_open)
    assert client.post(f"{URL}/test").json() == {"success": True, "delivery_status": 200}
    expected = hmac.new(secret.encode(), sent["body"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sent["sig"], expected)


def test_audit_log_has_no_secret(client: APIClient, company: Company, admin_user: User) -> None:
    secret = client.post(ROTATE).json()["secret"]
    log = AuditLog.objects.get(action="settings.webhook_secret_rotated")
    assert log.company_id == company.pk and log.actor_id == admin_user.pk
    dumped = json.dumps({f.name: str(getattr(log, f.name)) for f in AuditLog._meta.fields})
    assert secret not in dumped and secret[-4:] not in json.dumps(log.changes or {})


def test_member_cannot_rotate(member_client: APIClient, company: Company) -> None:
    assert member_client.post(ROTATE).status_code == 403
    company.refresh_from_db()
    assert company.webhook_secret == ""
    assert not AuditLog.objects.filter(action="settings.webhook_secret_rotated").exists()


def test_rate_limited_to_5_per_hour_per_company(client: APIClient, company: Company) -> None:
    secrets_seen = {client.post(ROTATE).json()["secret"] for _ in range(5)}
    assert len(secrets_seen) == 5
    company.refresh_from_db()
    kept = company.webhook_secret
    blocked = client.post(ROTATE)
    assert blocked.status_code == 429
    assert "secret" not in json.dumps(blocked.json())
    company.refresh_from_db()
    assert company.webhook_secret == kept  # nothing rotated
    # Shared by every admin of the company.
    other_admin = User.objects.create_user(
        username="admin2@cabinet-co", company=company, is_company_admin=True
    )
    api = APIClient()
    api.force_authenticate(user=other_admin)
    assert api.post(ROTATE).status_code == 429
