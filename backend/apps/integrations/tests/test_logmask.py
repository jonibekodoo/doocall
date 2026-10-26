"""Secret path tokens never reach the production JSON logs — including the
``request`` repr and other extra attributes the JSON formatter serializes."""

from __future__ import annotations

import io
import json
import logging
import logging.config
from collections.abc import Iterator
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.integrations.logmask import MaskedProxy, SecretPathFilter, mask
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db

C2C_TOKEN = "tok-" + "c" * 40
KOTIB_TOKEN = "kot-" + "k" * 40
REC_SIG = "f" * 64


@pytest.fixture
def json_log() -> Iterator[io.StringIO]:
    """django.request rendered by the production LOGGING "json" formatter."""
    formatter = logging.config.DictConfigurator(settings.LOGGING).configure_formatter(
        dict(settings.LOGGING["formatters"]["json"])
    )
    assert type(formatter).__name__ == "JsonFormatter"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger = logging.getLogger("django.request")
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


@pytest.fixture
def integrations(company: Company) -> None:
    CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={
            "webhook_url": "https://b24.example.com/rest/1/hook/",
            "click_to_call_enabled": True,
            "c2c_token": C2C_TOKEN,
            "b24_app_token": "app-secret-token",
        },
    )
    CrmIntegration.all_objects.create(
        company=company,
        provider="kotib",
        is_enabled=True,
        config={"analysis_token": KOTIB_TOKEN, "analysis_secret": "kotib-analysis-secret"},
    )


def _records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_401_and_403_json_records_carry_no_token(json_log: io.StringIO, integrations: None) -> None:
    client = APIClient()
    c2c = client.post(
        f"/api/public/bitrix24/click-to-call/{C2C_TOKEN}",
        {"event": "ONEXTERNALCALLSTART", "auth[application_token]": "wrong"},
    )
    kotib = client.post(
        f"/api/public/kotib/analysis/{KOTIB_TOKEN}",
        "{}",
        content_type="application/json",
        HTTP_X_KOTIB_SIGNATURE="deadbeef",
    )
    rec = client.get(f"/api/public/rec/abc123?sig={REC_SIG}")
    assert (c2c.status_code, kotib.status_code, rec.status_code) == (401, 401, 403)

    records = _records(json_log)
    assert len(records) == 3, json_log.getvalue()
    output = json_log.getvalue()
    for secret in (C2C_TOKEN, KOTIB_TOKEN, REC_SIG, "c" * 20, "k" * 20):
        assert secret not in output
    requests = " ".join(r["request"] for r in records)
    assert "<WSGIRequest: POST '/api/public/bitrix24/click-to-call/tok-***'>" in requests
    assert "<WSGIRequest: POST '/api/public/kotib/analysis/kot-***'>" in requests
    assert "/api/public/rec/abc123?sig=***" in requests
    assert all(r["name"] == "django.request" and r["levelname"] == "WARNING" for r in records)


def test_request_object_itself_is_not_mutated() -> None:
    class FakeRequest:
        path = f"/api/public/kotib/analysis/{KOTIB_TOKEN}"
        method = "POST"

        def __repr__(self) -> str:
            return f"<FakeRequest: POST '{self.path}'>"

    request = FakeRequest()
    record = logging.makeLogRecord(
        {"msg": "Unauthorized: %s", "args": (request.path,), "request": request}
    )
    SecretPathFilter().filter(record)
    assert isinstance(record.request, MaskedProxy)
    assert KOTIB_TOKEN not in str(record.request) + repr(record.request)
    assert record.request.method == "POST"  # delegated for other handlers
    assert record.request_path == "/api/public/kotib/analysis/kot-***"
    assert request.path.endswith(KOTIB_TOKEN)  # the app's object is untouched
    assert KOTIB_TOKEN not in record.getMessage()


def test_other_extra_attributes_are_scanned() -> None:
    url = f"https://x.uz/api/public/rec/9?a=1&sig={REC_SIG}"
    record = logging.makeLogRecord(
        {
            "msg": "ok",
            "target": url,
            "obj": type(
                "O", (), {"__str__": lambda self: f"/api/public/kotib/analysis/{KOTIB_TOKEN}"}
            )(),
            "status_code": 401,
        }
    )
    SecretPathFilter().filter(record)
    assert record.target == "https://x.uz/api/public/rec/9?a=1&sig=***"
    assert KOTIB_TOKEN not in str(record.obj)
    assert record.status_code == 401


def test_mask_patterns() -> None:
    assert mask(f"/api/public/rec/srv_1?sig={REC_SIG}") == "/api/public/rec/srv_1?sig=***"
    assert mask(f"'/api/public/rec/1?x=2&sig={REC_SIG}'") == "'/api/public/rec/1?x=2&sig=***'"
    assert mask("/api/public/rec/1?design=a") == "/api/public/rec/1?design=a"
    assert mask("/api/v1/calls?sig=keep") == "/api/v1/calls?sig=keep"
