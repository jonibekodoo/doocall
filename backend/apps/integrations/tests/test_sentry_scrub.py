"""Sentry before_send / before_breadcrumb strip secret path tokens, ?sig=
and signature headers (fake event dicts shaped like sentry-sdk's)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from apps.integrations.logmask import sentry_before_breadcrumb, sentry_before_send

C2C = "tok-" + "c" * 40
KOTIB = "kot-" + "k" * 40
SIG = "f" * 64
SIGNATURE = "sha256=" + "e" * 64
BACKEND = Path(__file__).resolve().parents[3]

SECRETS = (C2C, KOTIB, SIG, SIGNATURE, "c" * 20, "k" * 20, "Assalomu")


def _clean(obj: Any) -> str:
    text = json.dumps(obj)
    for secret in SECRETS:
        assert secret not in text, secret
    return text


def _event(url: str, query: Any = "", **request: Any) -> dict[str, Any]:
    return {
        "transaction": urlsplit(url).path,
        "request": {
            "url": url,
            "method": "POST",
            "query_string": query,
            "headers": {
                "Referer": f"https://acme.doocall.uz/api/public/kotib/analysis/{KOTIB}",
                "X-Kotib-Signature": SIGNATURE,
                "Content-Type": "application/json",
            },
            "data": {"conversation_text": "Assalomu alaykum"},
            **request,
        },
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": f"bad /api/public/bitrix24/click-to-call/{C2C} call",
                    "stacktrace": {"frames": [{"vars": {"path": f"/api/public/rec/1?sig={SIG}"}}]},
                }
            ]
        },
        "logentry": {"message": f"Unauthorized: /api/public/kotib/analysis/{KOTIB}"},
        "breadcrumbs": {"values": [{"data": {"url": f"/api/public/rec/1?a=1&sig={SIG}"}}]},
    }


def test_kotib_event_is_scrubbed() -> None:
    event = sentry_before_send(_event(f"https://acme.doocall.uz/api/public/kotib/analysis/{KOTIB}"))
    text = _clean(event)
    request = event["request"]
    assert request["url"] == "https://acme.doocall.uz/api/public/kotib/analysis/kot-***"
    assert "X-Kotib-Signature" not in request["headers"]
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["Referer"].endswith("/api/public/kotib/analysis/kot-***")
    assert "data" not in request  # public webhook bodies dropped
    assert event["transaction"] == "/api/public/kotib/analysis/kot-***"
    assert "/api/public/bitrix24/click-to-call/tok-***" in text
    assert "/api/public/rec/1?a=1&sig=***" in text


def test_rec_query_string_sig_masked() -> None:
    event = sentry_before_send(
        _event("https://acme.doocall.uz/api/public/rec/srv_1", query=f"x=1&sig={SIG}")
    )
    _clean(event)
    assert event["request"]["query_string"] == "x=1&sig=***"
    dict_query = sentry_before_send(
        _event("https://acme.doocall.uz/api/public/rec/srv_1", query={"sig": SIG})
    )
    assert dict_query["request"]["query_string"] == {"sig": "***"}


def test_query_string_list_of_pairs_sig_masked() -> None:
    """Tester gap 1: query_string as [[name, value], …] — on a rec link and
    on any other URL (key-based, not URL-based)."""
    for url in ("https://acme.doocall.uz/api/public/rec/srv_1", "https://acme.doocall.uz/x"):
        event = sentry_before_send(_event(url, query=[["x", "1"], ["sig", SIG]], data={}))
        _clean(event)
        assert event["request"]["query_string"] == [["x", "1"], ["sig", "***"]]
    string_form = sentry_before_send(_event("https://acme.doocall.uz/x", query=f"sig={SIG}"))
    assert string_form["request"]["query_string"] == "sig=***"


def test_bare_sig_and_sig_variables_masked() -> None:
    """Tester gap 2: a frame variable holding only the query string (no rec
    path), and RecordRedirectView's own local ``sig``."""
    event = _event("https://acme.doocall.uz/api/public/rec/srv_1")
    event["exception"]["values"][0]["stacktrace"]["frames"] = [
        {
            "function": "get",
            "vars": {
                "query": f"sig={SIG}",
                "full": f"?a=1&sig={SIG}",
                "quoted": f"'sig={SIG}'",
                "sig": f"'{SIG}'",
                "params": [("sig", SIG)],
                "design": "keep=1",
            },
        }
    ]
    event = sentry_before_send(event)
    _clean(event)
    frame_vars = event["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame_vars == {
        "query": "sig=***",
        "full": "?a=1&sig=***",
        "quoted": "'sig=***'",
        "sig": "***",
        "params": [["sig", "***"]],
        "design": "keep=1",
    }
    crumb = sentry_before_breadcrumb({"message": f"GET ?sig={SIG}", "data": {"sig": SIG}})
    assert crumb == {"message": "GET ?sig=***", "data": {"sig": "***"}}


def test_header_list_form_and_non_public_body_kept() -> None:
    event = sentry_before_send(
        _event(
            "https://acme.doocall.uz/api/web/v1/calls",
            headers=[["x-kotib-signature", SIGNATURE], ["Accept", "*/*"]],
            data={"note": "kept"},
        )
    )
    assert event["request"]["headers"] == [["Accept", "*/*"]]
    assert event["request"]["data"] == {"note": "kept"}


def test_breadcrumb_scrubbed() -> None:
    crumb = sentry_before_breadcrumb(
        {
            "category": "httplib",
            "message": f"POST /api/public/bitrix24/click-to-call/{C2C}",
            "data": {"url": f"https://acme.doocall.uz/api/public/rec/9?sig={SIG}", "status": 403},
        }
    )
    _clean(crumb)
    assert crumb["message"] == "POST /api/public/bitrix24/click-to-call/tok-***"
    assert crumb["data"] == {
        "url": "https://acme.doocall.uz/api/public/rec/9?sig=***",
        "status": 403,
    }


def test_settings_wire_hooks_into_sentry() -> None:
    script = (
        "import django; django.setup(); import sentry_sdk; "
        "o = sentry_sdk.get_client().options; "
        "print(o['before_send'].__name__, o['before_send_transaction'].__name__, "
        "o['before_breadcrumb'].__name__, o['send_default_pii'])"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter + inline script
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "doocall.settings",
            "SENTRY_DSN": "https://public@o0.ingest.sentry.io/1",  # never contacted
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert result.stdout.split() == [
        "sentry_before_send",
        "sentry_before_send",
        "sentry_before_breadcrumb",
        "False",
    ]
