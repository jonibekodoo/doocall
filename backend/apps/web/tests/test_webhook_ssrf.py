"""Custom company webhook (Company.webhook_url) behind the SSRF guard."""

from __future__ import annotations

import socket
import threading
import urllib.error
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core import netguard
from apps.web import tasks as web_tasks

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/webhook"


@pytest.mark.parametrize(
    "url",
    [
        "http://crm.example.uz/hook",  # plain http outside DEBUG
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/hook",
        "https://minio:9000/doocall-recordings",
        "https://redis/",
        "https://user:pw@crm.example.uz/hook",
        "https://crm.example.uz:8443/hook",
        "ftp://crm.example.uz/hook",
    ],
)
def test_save_rejects_blocked_urls(client: APIClient, company: Company, url: str) -> None:
    response = client.put(URL, {"url": url}, format="json")
    assert response.status_code == 400
    assert response.json()["message"].startswith("Webhook manzili rad etildi:")
    company.refresh_from_db()
    assert company.webhook_url == ""


def test_save_rejects_name_resolving_to_private(
    client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: ["172.18.0.3"])
    response = client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json")
    assert response.status_code == 400 and "ichki" in response.json()["message"]


def test_save_accepts_public_https_and_clearing(client: APIClient, company: Company) -> None:
    body = client.put(URL, {"url": "https://crm.example.uz/hook"}, format="json").json()
    assert body["webhook_url"] == "https://crm.example.uz/hook" and body["secret"]
    assert client.put(URL, {"url": ""}, format="json").status_code == 200


@pytest.fixture
def record(company: Company) -> CallRecord:
    return CallRecord.all_objects.create(
        company=company,
        call_id="w-1",
        call_type="inbound",
        call_status="answered",
        from_number="+998901234567",
        to_number="+998998887766",
        counterparty_number="+998901234567",
        duration=5,
        start_time=timezone.now(),
    )


def _set_url(company: Company, url: str) -> None:
    # Bypass the save-time check (simulates rows stored before the guard);
    # update the instance the authenticated client holds as well.
    Company.objects.filter(pk=company.pk).update(webhook_url=url, webhook_secret="s" * 64)
    company.webhook_url, company.webhook_secret = url, "s" * 64


def test_stored_internal_url_is_not_called_nor_retried(
    company: Company,
    record: CallRecord,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Webhooks saved before the guard: the task gives up cleanly — no
    connection, no exception (so Celery's autoretry never fires)."""
    _set_url(company, "http://minio:9000/doocall-recordings")

    def no_connect(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not connect")

    monkeypatch.setattr(socket, "create_connection", no_connect)
    assert web_tasks.deliver_call_webhook(record.pk) == 0
    assert "xavfsizlik tekshiruvidan o'tmadi" in caplog.text
    assert "minio" not in caplog.text  # URL not logged


def test_task_retries_only_on_transient_errors(
    company: Company, record: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_url(company, "https://crm.example.uz/hook")

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr(netguard, "open_url", boom)
    with pytest.raises(OSError):  # propagates → Celery autoretry
        web_tasks.deliver_call_webhook(record.pk)


def test_test_endpoint_reports_block_actionably(client: APIClient, company: Company) -> None:
    _set_url(company, "https://169.254.169.254/latest/")
    response = client.post(f"{URL}/test")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error.startswith("Webhook manzili xavfsizlik tekshiruvidan o'tmadi:")
    assert "Sozlamalar" in error


# ── Real HTTP against a local server (pinned, no redirects, no echo) ──────
class _Hook(BaseHTTPRequestHandler):
    hits: list[tuple[str, str | None, str | None]] = []
    reply: tuple[int, dict[str, str], bytes] = (204, {}, b"")
    queue: list[tuple[int, dict[str, str], bytes]] = []  # one-shot replies first

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        _Hook.hits.append(
            (self.path, self.headers.get("Host"), self.headers.get("X-Doocall-Signature"))
        )
        status, headers, body = _Hook.queue.pop(0) if _Hook.queue else _Hook.reply
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def hook_server(settings: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """http://hooks.example.com:<port> served locally: the guard's checks
    run for real, only the vetted IP is our loopback server (DEBUG lets
    plain http and the port through)."""
    settings.DEBUG = True
    _Hook.hits, _Hook.reply, _Hook.queue = [], (204, {}, b""), []
    httpd = HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    real_check = netguard.check_url
    monkeypatch.setattr(netguard, "check_url", lambda url: (real_check(url)[0], "127.0.0.1"))
    yield f"http://hooks.example.com:{httpd.server_port}"
    httpd.shutdown()


def test_valid_url_delivers_signed_to_pinned_ip(
    company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    assert web_tasks.deliver_call_webhook(record.pk) == 204
    path, host, signature = _Hook.hits[0]
    assert path == "/hook" and host == hook_server.removeprefix("http://")
    assert signature and len(signature) == 64


def test_redirect_is_not_followed_nor_retried(
    company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.reply = (302, {"Location": "http://169.254.169.254/"}, b"")
    assert web_tasks.deliver_call_webhook(record.pk) == 0
    assert len(_Hook.hits) == 1


def test_test_endpoint_does_not_echo_remote_body(
    client: APIClient, company: Company, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.reply = (500, {"Content-Type": "text/html"}, b"<h1>internal stack trace SECRET</h1>")
    response = client.post(f"{URL}/test")
    assert response.status_code == 502
    assert response.json() == {"success": False, "error": "HTTP 500"}
    _Hook.reply = (204, {}, b"")
    assert client.post(f"{URL}/test").json() == {"success": True, "delivery_status": 204}


# ── Delivery outcome: retry policy, last status, log hygiene ──────────────
def _deliver(record: CallRecord) -> int:
    """Run through Celery (eager ``apply``) so retries really happen."""
    return int(web_tasks.deliver_call_webhook.apply(args=[record.pk]).get())


def _task_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "apps.web.tasks" and r.levelname == "WARNING"
    ]


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_4xx_is_permanent_not_retried_and_status_saved(
    company: Company,
    record: CallRecord,
    hook_server: str,
    caplog: pytest.LogCaptureFixture,
    code: int,
) -> None:
    _set_url(company, f"{hook_server}/hook/tok3n")
    _Hook.reply = (code, {"Content-Type": "text/html"}, b"<h1>SECRET remote body</h1>")
    assert _deliver(record) == 0
    assert len(_Hook.hits) == 1  # no retry

    company.refresh_from_db()
    assert company.webhook_last_status == f"http_{code}"
    assert company.webhook_last_error_at is not None
    assert company.webhook_last_ok_at is None

    (line,) = _task_warnings(caplog)  # exactly one WARNING
    assert f"company {company.pk}" in line and f"call {record.pk}" in line
    assert f"http_{code}" in line and "giving up" in line
    for leak in ("hooks.example.com", "tok3n", "/hook", "SECRET", hook_server):
        assert leak not in caplog.text


@pytest.mark.parametrize("code", [500, 502, 503, 408, 429])
def test_5xx_408_429_are_retried_then_saved(
    company: Company,
    record: CallRecord,
    hook_server: str,
    caplog: pytest.LogCaptureFixture,
    code: int,
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.reply = (code, {}, b"")
    assert _deliver(record) == 0
    assert len(_Hook.hits) == 4  # first attempt + max_retries (3)

    company.refresh_from_db()
    assert company.webhook_last_status == f"http_{code}"
    warnings = _task_warnings(caplog)
    assert len(warnings) == 4
    assert all(f"http_{code}" in w for w in warnings)
    assert "will retry" in warnings[0] and "giving up" in warnings[-1]


def test_only_the_final_outcome_is_saved(
    company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.queue = [(500, {}, b""), (503, {}, b"")]  # then the default 204
    assert _deliver(record) == 204
    assert len(_Hook.hits) == 3

    company.refresh_from_db()
    assert company.webhook_last_status == "ok"
    assert company.webhook_last_ok_at is not None
    assert company.webhook_last_error_at is None  # retries are not outcomes


def test_success_after_an_earlier_failure_keeps_the_error_time(
    company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.reply = (404, {}, b"")
    _deliver(record)
    company.refresh_from_db()
    failed_at = company.webhook_last_error_at

    _Hook.reply = (200, {}, b"")
    assert _deliver(record) == 200
    company.refresh_from_db()
    assert company.webhook_last_status == "ok"
    assert company.webhook_last_error_at == failed_at
    assert company.webhook_last_ok_at > failed_at


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (TimeoutError("timed out"), "timeout"),
        (urllib.error.URLError(TimeoutError("timed out")), "timeout"),
        (urllib.error.URLError(ConnectionRefusedError(111, "refused")), "connection_error"),
        (ConnectionResetError(104, "reset"), "connection_error"),
    ],
)
def test_network_errors_are_retried_and_classified(
    company: Company,
    record: CallRecord,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: str,
) -> None:
    _set_url(company, "https://crm.example.uz/hook")
    attempts: list[int] = []

    def fail(*args: Any, **kwargs: Any) -> Any:
        attempts.append(1)
        raise error

    monkeypatch.setattr(netguard, "open_url", fail)
    assert _deliver(record) == 0
    assert len(attempts) == 4
    company.refresh_from_db()
    assert company.webhook_last_status == status


def test_blocked_url_saves_blocked_without_retry(
    company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    _Hook.reply = (302, {"Location": "http://169.254.169.254/"}, b"")
    assert _deliver(record) == 0
    assert len(_Hook.hits) == 1
    company.refresh_from_db()
    assert company.webhook_last_status == "blocked"


def test_settings_get_exposes_last_delivery(
    client: APIClient, company: Company, record: CallRecord, hook_server: str
) -> None:
    _set_url(company, f"{hook_server}/hook")
    fresh = client.get(URL).json()
    assert (fresh["last_status"], fresh["last_ok_at"], fresh["last_error_at"]) == (
        None,
        None,
        None,
    )

    _Hook.reply = (404, {}, b"")
    _deliver(record)
    company.refresh_from_db()  # the forced-auth user holds this very instance
    body = client.get(URL).json()
    assert body["last_status"] == "http_404"
    assert body["last_error_at"] == company.webhook_last_error_at.isoformat()
    assert body["last_ok_at"] is None
    assert set(body) == {
        "success",
        "webhook_url",
        "secret_set",
        "last_status",
        "last_ok_at",
        "last_error_at",
    }


def test_settings_get_is_company_admin_only(company: Company) -> None:
    member = User.objects.create_user(
        username="member@w.uz", company=company, is_company_admin=False
    )
    api = APIClient()
    api.force_authenticate(member)
    assert api.get(URL).status_code == 403
