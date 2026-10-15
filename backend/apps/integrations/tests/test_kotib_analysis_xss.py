"""Extra adversarial checks for the Kotib analysis webhook → cabinet API."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.calls.models import CallRecord
from apps.integrations.models import CallAnalysis, CrmIntegration
from apps.integrations.tests.test_kotib_analysis import (  # noqa: F401
    AI,
    _payload,
    _send,
    kotib,
)

pytestmark = pytest.mark.django_db

VECTORS = [
    "<svg onload=alert(1)>",
    "<svg><script>alert(1)</script></svg>",
    '<a href="JaVaScRiPt:alert(1)">x</a>',
    '<a href="&#106;avascript:alert(1)">x</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
    "<math><mi xlink:href=javascript:alert(1)>",
    '<img src="x" onerror="alert(1)">',
    "<body onload=alert(1)>",
    "<form action=javascript:alert(1)><button>x</button></form>",
    "<style>*{background:url(javascript:alert(1))}</style>",
    '<object data="javascript:alert(1)"></object>',
    "<scr<script>ipt>alert(1)</scr</script>ipt>",
]


@pytest.mark.parametrize("vector", VECTORS)
def test_hostile_comment_never_reaches_cabinet_api(
    kotib: CrmIntegration, call: CallRecord, client: APIClient, vector: str
) -> None:
    payload = _payload(call)
    payload["prompt_scores"][0]["comment"] = f"<b>ok</b>{vector}"
    assert _send(kotib, payload).status_code == 200
    analysis = CallAnalysis.all_objects.get()
    detail = client.get(f"{AI}/analyses/{analysis.pk}").json()["analysis"]
    html = detail["prompt_scores"][0]["comment_html"].lower()
    for bad in ("<script", "<svg", "<style", "<object", "<form", "<body", "<math", "<img",
                "onerror", "onload", "javascript:", "data:", "href"):
        assert bad not in html, (vector, html)
    assert "<b>ok</b>" in html


def test_kotib_media_url_not_exposed(
    kotib: CrmIntegration, call: CallRecord, client: APIClient
) -> None:
    _send(kotib, _payload(call))
    analysis = CallAnalysis.all_objects.get()
    text = client.get(f"{AI}/analyses/{analysis.pk}").content.decode()
    text += client.get(f"{AI}/analyses").content.decode()
    assert "secret.wav" not in text and "business.kotib.ai" not in text
