"""SSRF guard for company-configured CRM URLs (apps.core.netguard) and the
generic, non-echoing error handling of providers._http_json."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core import netguard
from apps.integrations import providers
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "url",
    [
        "http://acme.bitrix24.ru/rest/1/tok/",  # plain http outside DEBUG
        "ftp://acme.bitrix24.ru/",
        "https://127.0.0.1/rest/1/tok/",
        "https://10.0.0.5/",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/",
        "https://minio/doocall-recordings",  # Docker service name
        "https://minio:9000/",
        "https://localhost/",
        "https://crm.internal/",
        "https://printer.local/",
        "https://user:pw@acme.bitrix24.ru/",
        "https://acme.bitrix24.ru:8443/",
        "https://acme.bitrix24.ru@evil.example/",
        "https://app.doocall.uz/api/",  # our own domains
        "https://acme.doocall.uz/",
        "",
    ],
)
def test_blocked_urls(url: str, settings: Any) -> None:
    settings.DOMAIN_ROOT = "doocall.uz"
    settings.DOMAIN_APP = "app.doocall.uz"
    with pytest.raises(netguard.UnsafeURL):
        netguard.check_url(url)


@pytest.mark.parametrize(
    "addresses",
    [
        ["10.1.2.3"],
        ["192.168.0.10"],
        ["172.18.0.4"],  # docker bridge
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["100.64.1.1"],  # CGNAT
        ["0.0.0.0"],
        ["224.0.0.1"],
        ["::1"],
        ["fd00::1"],  # ULA
        ["fe80::1"],
        ["::ffff:10.0.0.1"],  # IPv4-mapped private
        ["2002:7f00:1::1"],  # 6to4 of 127.0.0.1
        ["2001:0:4136:e378:8000:63bf:f5ff:fffe"],  # Teredo, client 10.0.0.1
        ["64:ff9b::7f00:1"],  # NAT64 of 127.0.0.1 (Tester's gap)
        ["64:ff9b::a00:1"],  # NAT64 of 10.0.0.1 (Tester's gap)
        ["64:ff9b::a9fe:a9fe"],  # NAT64 of 169.254.169.254
        ["64:ff9b:1::808:808"],  # local-use NAT64 prefix — refused outright
        ["::127.0.0.1"],  # IPv4-compatible (Tester's gap)
        ["::8.8.8.8"],  # IPv4-compatible range refused even for public IPv4
        ["198.18.0.1"],  # benchmarking
        ["192.0.0.8"],  # IETF protocol assignments
        ["93.184.216.34", "10.0.0.1"],  # ANY private → blocked
    ],
)
def test_name_resolving_to_private_is_blocked(
    addresses: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: addresses)
    with pytest.raises(netguard.UnsafeURL, match="ichki"):
        netguard.check_url("https://crm.example.com/rest/")


@pytest.mark.parametrize("address", ["64:ff9b::808:808", "2606:4700::1111", "8.8.8.8"])
def test_public_nat64_and_ipv6_pass(address: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: [address])
    assert netguard.check_url("https://crm.example.com/")[1] == address


def test_unresolvable_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(host: str, port: int) -> list[str]:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(netguard, "resolve", fail)
    with pytest.raises(netguard.UnsafeURL, match="DNS"):
        netguard.check_url("https://nope.example.com/")


def test_public_https_passes_and_pins_first_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: ["93.184.216.34", "2606:2800::1"])
    parts, ip = netguard.check_url("https://acme.bitrix24.ru/rest/1/tok/")
    assert parts.hostname == "acme.bitrix24.ru" and ip == "93.184.216.34"


def test_debug_allows_http_and_ports(settings: Any) -> None:
    settings.DEBUG = True
    netguard.check_url("http://crm.example.com:8069/")


# ── Real HTTP against a local server (pinned connection) ──────────────────
class _Server(BaseHTTPRequestHandler):
    hits: list[tuple[str, str | None]] = []
    replies: list[tuple[int, dict[str, str], bytes]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        _Server.hits.append((self.path, self.headers.get("Host")))
        status, headers, body = _Server.replies.pop(0)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST  # noqa: N815

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def server(settings: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A local HTTP server reachable as http://crm.example.com:<port> — the
    guard's check is real except that the vetted IP is our loopback server
    (DEBUG lets plain http and the port through)."""
    settings.DEBUG = True
    _Server.hits, _Server.replies = [], []
    httpd = HTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    real_check = netguard.check_url

    def check(url: str) -> Any:
        parts, _ = real_check(url)
        return parts, "127.0.0.1"

    monkeypatch.setattr(netguard, "check_url", check)
    yield f"http://crm.example.com:{httpd.server_port}"
    httpd.shutdown()


def test_connection_is_pinned_to_vetted_ip(server: str) -> None:
    _Server.replies = [(200, {"Content-Type": "application/json"}, b'{"result": {"ID": 1}}')]
    body = providers._http_json(f"{server}/rest/profile.json", {})
    assert body == {"result": {"ID": 1}}
    # "crm.example.com" never resolved — the socket went to the vetted IP,
    # while the Host header still names the CRM.
    assert _Server.hits == [("/rest/profile.json", f"crm.example.com:{server.rsplit(':', 1)[1]}")]


def test_redirect_is_not_followed_and_location_not_echoed(server: str) -> None:
    _Server.replies = [(302, {"Location": "http://169.254.169.254/secret-path"}, b"")]
    with pytest.raises(providers.ProviderError) as exc:
        providers._http_json(f"{server}/rest/profile.json", {})
    assert str(exc.value) == "HTTP 302: redirect refused"
    assert len(_Server.hits) == 1


def test_html_error_body_is_not_echoed(server: str) -> None:
    _Server.replies = [
        (403, {"Content-Type": "text/html"}, b"<html>internal admin panel v1.2</html>")
    ]
    with pytest.raises(providers.ProviderError) as exc:
        providers._http_json(f"{server}/x", {})
    assert str(exc.value) == "HTTP 403"


def test_json_error_keeps_known_fields_only(server: str) -> None:
    body = {
        "error": "insufficient_scope",
        "error_description": "<b>needs</b> <script>x</script>user scope" + "!" * 300,
        "internal_dump": "SECRET",
    }
    _Server.replies = [(401, {"Content-Type": "application/json"}, json.dumps(body).encode())]
    with pytest.raises(providers.ProviderError) as exc:
        providers._http_json(f"{server}/x", {})
    message = str(exc.value)
    assert message.startswith("HTTP 401: insufficient_scope; needs")
    assert "SECRET" not in message and "<" not in message
    assert len(message) <= len("HTTP 401: ") + 200


def test_amocrm_entity_not_found_still_detected(server: str) -> None:
    body = {"_total_items": 0, "errors": [{"title": "Entity not found", "status": 263}]}
    _Server.replies = [(400, {"Content-Type": "application/json"}, json.dumps(body).encode())]
    with pytest.raises(providers.ProviderError, match="Entity not found"):
        providers._http_json(f"{server}/api/v4/calls", [{}])


def test_connection_error_is_generic(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "check_url", lambda url: (None, "127.0.0.1"))
    settings.DEBUG = True
    with pytest.raises(providers.ProviderError) as exc:
        providers._http_json("http://crm.example.com:1/x", {})  # nothing listens on :1
    assert str(exc.value) == "connection failed"


# ── Save / request-time enforcement ───────────────────────────────────────
URL = "/api/web/v1/settings/integrations"


@pytest.mark.parametrize(
    ("provider", "config"),
    [
        ("bitrix24", {"webhook_url": "https://169.254.169.254/rest/1/x/"}),
        ("bitrix24", {"webhook_url": "http://acme.bitrix24.ru/rest/1/x/"}),
        ("amocrm", {"base_url": "https://minio:9000", "access_token": "t" * 20}),
        (
            "odoo",
            {"url": "https://127.0.0.1", "db": "d", "login": "l", "api_key": "k" * 20},
        ),
    ],
)
def test_save_rejects_unsafe_url(
    client: APIClient, company: Company, provider: str, config: dict[str, str]
) -> None:
    response = client.put(f"{URL}/{provider}", {"config": config}, format="json")
    assert response.status_code == 400
    assert response.json()["message"].startswith("CRM manzili rad etildi:")
    assert not CrmIntegration.all_objects.filter(company=company, provider=provider).exists()


def test_save_rejects_name_resolving_to_private(
    client: APIClient, company: Company, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: ["10.0.0.7"])
    response = client.put(
        f"{URL}/bitrix24",
        {"config": {"webhook_url": "https://acme.bitrix24.ru/rest/1/x/"}},
        format="json",
    )
    assert response.status_code == 400


def test_save_accepts_public_https(client: APIClient, company: Company) -> None:
    response = client.put(
        f"{URL}/bitrix24",
        {"is_enabled": True, "config": {"webhook_url": "https://acme.bitrix24.ru/rest/1/x/"}},
        format="json",
    )
    assert response.status_code == 200


def test_stored_bad_url_fails_at_request_time(
    company: Company, call: CallRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configs saved before the guard keep their URL — delivery refuses it
    without connecting, with an actionable message."""
    from apps.integrations import tasks

    integration = CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": "http://minio:9000/rest/1/x/"},
    )

    def no_connect(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("must not connect")

    monkeypatch.setattr(socket, "create_connection", no_connect)
    tasks.dispatch_call(call.pk)
    integration.refresh_from_db()
    assert integration.last_status == "error"
    assert "xavfsizlik tekshiruvidan o'tmadi" in integration.last_error
    assert "sozlamalarida manzilni tuzating" in integration.last_error


# ── Bitrix24 users endpoint ───────────────────────────────────────────────
@pytest.fixture
def bitrix(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": "https://acme.bitrix24.ru/rest/1/tok/"},
    )


def _fake_pages(monkeypatch: pytest.MonkeyPatch, *bodies: Any) -> list[Any]:
    calls: list[Any] = []
    queue = list(bodies)

    def fake(url: str, payload: Any = None, **_: Any) -> Any:
        calls.append(payload)
        body = queue.pop(0) if queue else {"result": [], "next": 0}
        if isinstance(body, Exception):
            raise body
        return body

    monkeypatch.setattr(providers, "_http_json", fake)
    return calls


def test_users_endpoint_returns_only_parsed_user_rows(
    client: APIClient, bitrix: CrmIntegration, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pages(
        monkeypatch,
        {
            "result": [
                {
                    "ID": "5",
                    "NAME": "<b>Ali</b>",
                    "LAST_NAME": "V",
                    "EMAIL": "a@x.uz",
                    "EXTRA": "secret",
                },
                {"ID": {"x": 1}, "NAME": "dict id"},
                {"ID": "abc", "NAME": "not a user"},
                {"NAME": "no id"},
                {"ID": "6", "NAME": {"nested": "x"}, "EMAIL": ["list"], "WORK_POSITION": 7},
                "raw string row",
            ]
        },
    )
    body = client.get(f"{URL}/bitrix24/users").json()
    assert body["users"] == [
        {"id": "5", "name": "Ali V", "email": "a@x.uz", "phone": "", "position": ""},
        {"id": "6", "name": "", "email": "", "phone": "", "position": "7"},
    ]
    assert "secret" not in json.dumps(body)


def test_users_paging_stops_on_empty_or_stuck_next(
    client: APIClient, bitrix: CrmIntegration, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_pages(monkeypatch, {"result": [], "next": 0})
    client.get(f"{URL}/bitrix24/users")
    assert len(calls) == 1
    page = [{"ID": str(i + 1), "NAME": "U"} for i in range(50)]
    calls = _fake_pages(monkeypatch, {"result": page, "next": 0}, {"result": page, "next": 0})
    client.get(f"{URL}/bitrix24/users")
    assert len(calls) == 1  # next didn't move forward


def test_users_paging_is_bounded(
    client: APIClient, bitrix: CrmIntegration, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = [{"ID": "1", "NAME": "U"}]  # tiny pages that never reach the row cap
    pages = [{"result": page, "next": n + 1} for n in range(50)]
    calls = _fake_pages(monkeypatch, *pages)
    client.get(f"{URL}/bitrix24/users")
    assert len(calls) == providers.B24_USERS_MAX_PAGES


def test_users_non_object_body_is_handled(
    client: APIClient, bitrix: CrmIntegration, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pages(monkeypatch, ["not", "an", "object"])
    response = client.get(f"{URL}/bitrix24/users")
    assert response.status_code == 200
    assert response.json()["success"] is False
