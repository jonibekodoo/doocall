"""Kotib: secrets (Kotib key, webhook_url token, webhook_secret) must not reach
logs, last_error / CrmDelivery.error, GET responses or AuditLog on any path."""

from __future__ import annotations

import json
import logging
import urllib.error
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.integrations import tasks
from apps.integrations.models import CrmDelivery, CrmIntegration
from apps.integrations.tests.test_kotib import (  # noqa: F401  (fixtures)
    CONNECTED,
    HOOK,
    KOTIB_KEY,
    URL,
    _connect,
    _row,
    kotib,
)

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "s3cr3t" * 4
TOKEN = "Xk3tokenq9"


def _no_secrets(text: str) -> None:
    for secret in (KOTIB_KEY, TOKEN, WEBHOOK_SECRET, HOOK):
        assert secret not in text


@pytest.fixture
def connected(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="kotib",
        is_enabled=True,
        config={"api_key": KOTIB_KEY, "webhook_url": HOOK, "webhook_secret": WEBHOOK_SECRET},
    )


@pytest.mark.parametrize(
    "failure",
    [
        500,
        401,
        410,
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
    ],
)
def test_delivery_failure_leaks_nothing(
    connected: CrmIntegration,
    call: CallRecord,
    kotib: Any,  # noqa: F811
    client: APIClient,
    caplog: pytest.LogCaptureFixture,
    failure: Any,
) -> None:
    kotib(failure)
    with caplog.at_level(logging.DEBUG):
        tasks.dispatch_call(call.pk)
    connected.refresh_from_db()
    _no_secrets(caplog.text)
    _no_secrets(connected.last_error)
    for delivery in CrmDelivery.all_objects.filter(call=call):
        _no_secrets(delivery.error)
    _no_secrets(json.dumps(client.get("/api/web/v1/settings/integrations").json()))


def test_connect_and_disconnect_logs_and_audit_clean(
    client: APIClient,
    company: Company,
    kotib: Any,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    kotib(CONNECTED, (500, {"success": False, "error_code": "X", "message": "boom"}))
    with caplog.at_level(logging.DEBUG):
        assert _connect(client).status_code == 200
        secret = _row(company).config["webhook_secret"]
        assert client.delete(URL).status_code == 200
    assert secret not in caplog.text
    _no_secrets(caplog.text)
    for audit in AuditLog.objects.all():
        text = json.dumps(audit.changes) + json.dumps(getattr(audit, "metadata", None) or {})
        _no_secrets(text)
        assert secret not in text


def test_failed_connect_logs_clean(
    client: APIClient,
    company: Company,
    kotib: Any,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    kotib((401, {"success": False, "error_code": "INVALID_API_KEY"}))
    with caplog.at_level(logging.DEBUG):
        assert _connect(client).status_code == 400
    _no_secrets(caplog.text)


def test_test_endpoint_response_clean(
    client: APIClient,
    company: Company,
    kotib: Any,  # noqa: F811
) -> None:
    kotib(CONNECTED, CONNECTED)
    _connect(client)
    response = client.post(f"{URL}/test")
    _no_secrets(response.content.decode())
    assert _row(company).config["webhook_secret"] not in response.content.decode()
