"""Kotib AI analysis results: inbound webhook, matching, cabinet AI API,
Kotib card settings (secret / rotate / disconnect)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import timedelta
from typing import Any

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.integrations import kotib_analysis as ka
from apps.integrations.models import CallAnalysis, CrmIntegration

pytestmark = pytest.mark.django_db

SECRET = "kotib-analysis-secret"
SETTINGS = "/api/web/v1/settings/integrations"
AI = "/api/web/v1/ai"


@pytest.fixture
def kotib(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="kotib",
        is_enabled=True,
        config={
            "api_key": "kotib-key-0123456789",
            "webhook_url": "https://kotib.test/api/v1/integration/doocall/x/webhook",
            "webhook_secret": "s" * 64,
            "doocall_api_key": "d" * 32,
            "analysis_token": "tok-" + "a" * 40,
        },
    )


def _url(integration: CrmIntegration) -> str:
    return f"/api/public/kotib/analysis/{integration.config['analysis_token']}"


def _payload(call: CallRecord | None = None, **overrides: Any) -> dict[str, Any]:
    start = (call.start_time if call else timezone.now()) + timedelta(seconds=30)
    body: dict[str, Any] = {
        "event": "analysis.completed",
        "audio_data_id": 3245062,
        "audio_file_id": 2949375,
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(seconds=65)).isoformat(),
        "final_score": 85.0,
        "conversation_text": "Agent: Assalomu alaykum. 00:00\n\nClient: Salom. 00:04",
        "audio_file_url": "https://business.kotib.ai/media/secret.wav",
        "prompt_scores": [
            {
                "key": "greeting_score",
                "name": "Greeting 10",
                "score": 10.0,
                "comment": "<div><b>Introduced</b> 10 / 10</div>",
                "is_violation": False,
            },
            {
                "key": "rudeness_score",
                "name": "Rudeness",
                "score": 0.0,
                "comment": "<div>Not found</div>",
                "is_violation": True,
            },
        ],
        "client_data": {
            "phone_number": "901112233",  # raw, as the telephony reports it
            "summary": "Returning client, two pizzas.",
            "answers": [
                {"key": "is_repeat", "name": "Returning client", "value": True},
                {"key": "items", "name": "Items", "value": ["Pizza", "Cola"]},
                {"key": "complaint", "name": "Complaint", "value": None},
            ],
        },
    }
    body.update(overrides)
    return body


def _send(
    integration: CrmIntegration,
    payload: dict[str, Any],
    *,
    secret: str | None = None,
    signature: str | None = None,
    host: str | None = None,
) -> Any:
    raw = json.dumps(payload).encode()
    headers: dict[str, str] = {}
    if secret is not None:
        headers["HTTP_X_KOTIB_SIGNATURE"] = hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()
    if signature is not None:
        headers["HTTP_X_KOTIB_SIGNATURE"] = signature
    if host:
        headers["HTTP_HOST"] = host
    return APIClient().generic(
        "POST",
        _url(integration),
        raw.decode(),
        content_type="application/json",
        **headers,  # type: ignore[arg-type]
    )


def _with_secret(integration: CrmIntegration) -> None:
    integration.config = {**integration.config, "analysis_secret": SECRET}
    integration.save()


class TestWebhook:
    def test_signed_payload_is_stored_and_matched(
        self, kotib: CrmIntegration, call: CallRecord, company: Company
    ) -> None:
        _with_secret(kotib)
        response = _send(kotib, _payload(call), secret=SECRET)
        assert response.status_code == 200, response.content
        assert response.json() == {"success": True, "status": "stored", "matched": True}
        analysis = CallAnalysis.all_objects.get(company=company)
        assert analysis.call_id == call.pk
        assert analysis.client_phone == "+998901112233"
        assert float(analysis.final_score) == 85.0
        assert analysis.signature_verified is True
        assert analysis.has_violation is False  # violation criterion scored 0
        assert analysis.client_answers[1]["value"] == ["Pizza", "Cola"]
        assert "secret.wav" not in json.dumps(
            {f.name: str(getattr(analysis, f.name)) for f in CallAnalysis._meta.fields}
        )

    def test_sha256_prefix_is_accepted(self, kotib: CrmIntegration, call: CallRecord) -> None:
        _with_secret(kotib)
        payload = _payload(call)
        raw = json.dumps(payload).encode()
        digest = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        response = APIClient().generic(
            "POST",
            _url(kotib),
            raw.decode(),
            content_type="application/json",
            HTTP_X_KOTIB_SIGNATURE=f"sha256={digest.upper()}",
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("signature", [None, "", "deadbeef", "sha256=00"])
    def test_bad_or_missing_signature_401(
        self, kotib: CrmIntegration, call: CallRecord, signature: str | None
    ) -> None:
        _with_secret(kotib)
        response = _send(kotib, _payload(call), signature=signature)
        assert response.status_code == 401
        assert not CallAnalysis.all_objects.exists()

    def test_wrong_secret_401(self, kotib: CrmIntegration, call: CallRecord) -> None:
        _with_secret(kotib)
        assert _send(kotib, _payload(call), secret="other").status_code == 401

    def test_unsigned_accepted_only_while_no_secret(
        self, kotib: CrmIntegration, call: CallRecord
    ) -> None:
        assert _send(kotib, _payload(call)).status_code == 200
        assert CallAnalysis.all_objects.get().signature_verified is False
        _with_secret(kotib)
        assert _send(kotib, _payload(call)).status_code == 401

    def test_unknown_token_404(self, kotib: CrmIntegration, call: CallRecord) -> None:
        raw = json.dumps(_payload(call)).encode()
        response = APIClient().generic(
            "POST", "/api/public/kotib/analysis/nope", raw.decode(), content_type="application/json"
        )
        assert response.status_code == 404

    def test_disabled_410(self, kotib: CrmIntegration, call: CallRecord) -> None:
        kotib.is_enabled = False
        kotib.save()
        assert _send(kotib, _payload(call)).status_code == 410

    def test_other_company_subdomain_404(
        self, kotib: CrmIntegration, call: CallRecord, settings: Any
    ) -> None:
        settings.DOMAIN_ROOT = "doocall.uz"
        assert _send(kotib, _payload(call), host="other.doocall.uz").status_code == 404
        assert _send(kotib, _payload(call), host="integr-co.doocall.uz").status_code == 200

    def test_other_events_ignored(self, kotib: CrmIntegration) -> None:
        response = _send(kotib, {"event": "analysis.started", "audio_data_id": 1})
        assert response.status_code == 200 and response.json()["status"] == "ignored"
        assert not CallAnalysis.all_objects.exists()

    def test_malformed_400(self, kotib: CrmIntegration) -> None:
        assert _send(kotib, _payload(audio_data_id="x")).status_code == 400
        assert _send(kotib, _payload(start_time="yesterday")).status_code == 400

    def test_body_too_large_413(self, kotib: CrmIntegration, call: CallRecord) -> None:
        payload = _payload(call, conversation_text="x" * (2 * 1024 * 1024 + 10))
        assert _send(kotib, payload).status_code == 413

    def test_duplicate_updates_latest_wins(self, kotib: CrmIntegration, call: CallRecord) -> None:
        _send(kotib, _payload(call))
        second = _payload(call, final_score=40.5)
        second["prompt_scores"][1]["score"] = -10.0
        assert _send(kotib, second).status_code == 200
        analysis = CallAnalysis.all_objects.get()
        assert float(analysis.final_score) == 40.5
        assert analysis.has_violation is True
        assert CallAnalysis.all_objects.count() == 1

    def test_comment_html_is_sanitized(self, kotib: CrmIntegration, call: CallRecord) -> None:
        payload = _payload(call)
        payload["prompt_scores"][0]["comment"] = (
            '<div onclick="steal()" style="color:red"><script>alert(1)</script>'
            '<img src=x onerror=alert(2)><a href="javascript:alert(3)">link</a>'
            "<b>ok</b><iframe src=//evil></iframe><table><tr><td>1</td></tr></table></div>"
        )
        _send(kotib, payload)
        comment = CallAnalysis.all_objects.get().prompt_scores[0]["comment"]
        for bad in ("script", "onclick", "onerror", "javascript", "<img", "<a", "style", "iframe"):
            assert bad not in comment
        assert "<b>ok</b>" in comment and "<td>1</td>" in comment

    def test_unmatched_then_matched_on_resend(
        self, kotib: CrmIntegration, call: CallRecord, company: Company
    ) -> None:
        payload = _payload(call, start_time=(call.start_time + timedelta(minutes=10)).isoformat())
        response = _send(kotib, payload)
        assert response.json()["matched"] is False
        assert CallAnalysis.all_objects.get().call_id is None
        # Re-send with the right time → matched now.
        assert _send(kotib, _payload(call)).json()["matched"] is True
        assert CallAnalysis.all_objects.get().call_id == call.pk

    def test_end_time_only_matches_by_call_end(
        self, kotib: CrmIntegration, call: CallRecord
    ) -> None:
        end = call.start_time + timedelta(seconds=call.duration + 20)
        payload = _payload(call, start_time=end.isoformat(), end_time=end.isoformat())
        assert _send(kotib, payload).json()["matched"] is True

    def test_nearest_call_wins(
        self, kotib: CrmIntegration, call: CallRecord, company: Company
    ) -> None:
        nearer = CallRecord.all_objects.create(
            company=company,
            call_id="c-2",
            call_type="inbound",
            call_status="answered",
            from_number=call.from_number,
            to_number=call.to_number,
            counterparty_number=call.counterparty_number,
            duration=30,
            start_time=call.start_time + timedelta(seconds=25),
        )
        _send(kotib, _payload(call))  # Kotib start = call.start + 30 s
        assert CallAnalysis.all_objects.get().call_id == nearer.pk

    def test_phone_uses_company_code(
        self, kotib: CrmIntegration, call: CallRecord, company: Company
    ) -> None:
        Company.objects.filter(pk=company.pk).update(phone_code="992")
        _send(kotib, _payload(call))
        assert CallAnalysis.all_objects.get().client_phone == "+992901112233"

    def test_tenant_isolation(self, kotib: CrmIntegration, call: CallRecord) -> None:
        other = Company.objects.create(name="Other", slug="other-co")
        CrmIntegration.all_objects.create(
            company=other,
            provider="kotib",
            is_enabled=True,
            config={"analysis_token": "tok-" + "b" * 40},
        )
        _send(kotib, _payload(call))
        assert CallAnalysis.all_objects.get().company_id == call.company_id
        assert not CallAnalysis.all_objects.filter(company=other).exists()


@pytest.fixture
def analysis(kotib: CrmIntegration, call: CallRecord) -> CallAnalysis:
    _send(kotib, _payload(call))
    return CallAnalysis.all_objects.get()


@pytest.fixture
def operator_user(operator: OperatorProfile) -> User:
    return operator.user


def _post_raw(integration: CrmIntegration, raw: bytes, **headers: str) -> Any:
    return APIClient().generic(
        "POST",
        _url(integration),
        raw.decode(),
        content_type="application/json",
        **headers,  # type: ignore[arg-type]
    )


def _digest(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


HEX_SECRET = "0f" * 32  # a secret Kotib may treat as hex-encoded key bytes


class TestSignatureVariants:
    """Kotib's real format isn't specified — every safe HMAC-SHA256 variant
    over the raw body is accepted; unsigned/plain-token never is."""

    @pytest.fixture(autouse=True)
    def _clean_cache(self) -> Any:
        cache.clear()
        yield
        cache.clear()

    @pytest.mark.parametrize(
        "encode",
        [
            lambda d: d.hex(),
            lambda d: d.hex().upper(),
            lambda d: "sha256=" + d.hex(),
            lambda d: "SHA256=" + d.hex(),
            lambda d: base64.b64encode(d).decode(),
            lambda d: base64.b64encode(d).decode().rstrip("="),
            lambda d: base64.urlsafe_b64encode(d).decode(),
            lambda d: base64.urlsafe_b64encode(d).decode().rstrip("="),
            lambda d: "sha256=" + base64.b64encode(d).decode(),
        ],
        ids=[
            "hex",
            "HEX",
            "sha256=hex",
            "SHA256=hex",
            "b64",
            "b64-nopad",
            "b64url",
            "b64url-nopad",
            "sha256=b64",
        ],
    )
    def test_digest_encodings(self, kotib: CrmIntegration, call: CallRecord, encode: Any) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        sig = encode(_digest(SECRET.encode(), raw))
        response = _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=sig)
        assert response.status_code == 200, response.content
        assert CallAnalysis.all_objects.get().signature_verified is True

    @pytest.mark.parametrize("as_hex", [False, True])
    def test_hex_looking_secret_as_text_or_bytes(
        self, kotib: CrmIntegration, call: CallRecord, as_hex: bool
    ) -> None:
        kotib.config = {**kotib.config, "analysis_secret": HEX_SECRET}
        kotib.save()
        raw = json.dumps(_payload(call)).encode()
        key = bytes.fromhex(HEX_SECRET) if as_hex else HEX_SECRET.encode()
        response = _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=_digest(key, raw).hex())
        assert response.status_code == 200

    def test_webhook_secret_sent_at_connect_is_accepted(
        self, kotib: CrmIntegration, call: CallRecord
    ) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        key = kotib.config["webhook_secret"].encode()
        assert (
            _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=_digest(key, raw).hex()).status_code == 200
        )

    @pytest.mark.parametrize(
        "header", ["HTTP_X_SIGNATURE", "HTTP_X_WEBHOOK_SIGNATURE", "HTTP_X_HUB_SIGNATURE_256"]
    )
    def test_alias_headers(self, kotib: CrmIntegration, call: CallRecord, header: str) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        sig = "sha256=" + _digest(SECRET.encode(), raw).hex()
        assert _post_raw(kotib, raw, **{header: sig}).status_code == 200

    def test_timestamped_scheme(self, kotib: CrmIntegration, call: CallRecord) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        sig = _digest(SECRET.encode(), b"1700000000." + raw).hex()
        response = _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=f"t=1700000000,v1={sig}")
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "signature",
        [
            SECRET,  # plain token equality
            "sha256=" + SECRET,
            "tok-" + "a" * 40,  # the URL token
            "s" * 64,  # webhook_secret itself
            "t=1,v1=",
        ],
    )
    def test_plain_secret_or_token_rejected(
        self, kotib: CrmIntegration, call: CallRecord, signature: str
    ) -> None:
        _with_secret(kotib)
        assert _send(kotib, _payload(call), signature=signature).status_code == 401
        assert not CallAnalysis.all_objects.exists()

    def test_signature_over_other_body_rejected(
        self, kotib: CrmIntegration, call: CallRecord
    ) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        sig = _digest(SECRET.encode(), raw + b" ").hex()
        assert _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=sig).status_code == 401

    def test_mismatch_diagnostics_carry_no_secrets(
        self,
        kotib: CrmIntegration,
        call: CallRecord,
        company: Company,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _with_secret(kotib)
        raw = json.dumps(_payload(call)).encode()
        bad = base64.b64encode(_digest(b"wrong", raw)).decode()
        with caplog.at_level(logging.WARNING, logger="apps.integrations.kotib_analysis"):
            assert _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=bad).status_code == 401
            assert _post_raw(kotib, raw, HTTP_X_KOTIB_SIGNATURE=bad).status_code == 401
        warnings = [r for r in caplog.records if "signature mismatch" in r.getMessage()]
        assert len(warnings) == 1  # one per company per 10 min
        text = warnings[0].getMessage()
        assert "X-Kotib-Signature" in text and f"'length': {len(bad)}" in text
        assert "'charset': 'base64'" in text and "'prefix': 'none'" in text
        assert f"body_len={len(raw)}" in text and "analysis_secret:utf8" in text
        assert "base64url-nopad" in text

        entries = ka.recent_rejections(company.pk)
        assert len(entries) == 2
        assert entries[0]["body_len"] == len(raw)
        assert entries[0]["content_type"] == "application/json"
        dumped = json.dumps(entries) + text
        for leak in (bad, SECRET, kotib.config["webhook_secret"], "Assalomu", "tok-"):
            assert leak not in dumped

    def test_missing_header_diagnostics(self, kotib: CrmIntegration, company: Company) -> None:
        _with_secret(kotib)
        assert _send(kotib, _payload()).status_code == 401
        (entry,) = ka.recent_rejections(company.pk)
        assert entry["headers_present"] == [] and entry["signatures"] == []

    def test_rejection_log_keeps_last_20(self, kotib: CrmIntegration, company: Company) -> None:
        _with_secret(kotib)
        for _ in range(23):
            _send(kotib, _payload(), signature="deadbeef")
        assert len(ka.recent_rejections(company.pk)) == 20


class TestCabinetApi:
    def test_status(self, client: APIClient, analysis: CallAnalysis) -> None:
        body = client.get(f"{AI}/status").json()
        assert body == {
            "success": True,
            "kotib_connected": True,
            "has_analyses": True,
            "is_admin": True,
        }

    def test_status_without_kotib(self, client: APIClient) -> None:
        body = client.get(f"{AI}/status").json()
        assert body["kotib_connected"] is False and body["has_analyses"] is False

    def test_list_filters_and_summary(
        self, client: APIClient, analysis: CallAnalysis, kotib: CrmIntegration
    ) -> None:
        body = client.get(f"{AI}/analyses").json()
        assert body["count"] == 1 and body["pages"] == 1 and body["page"] == 1
        assert body["summary"] == {"count": 1, "avg_score": 85.0, "violations": 0}
        row = body["analyses"][0]
        assert row["id"] == analysis.pk and row["call_id"] == analysis.call_id
        assert analysis.call is not None
        assert row["operator"] == {"id": analysis.call.operator_id, "full_name": "Op One"}
        assert row["phone"] == "+998901112233" and row["final_score"] == 85.0
        assert row["summary"] == "Returning client, two pizzas." and row["has_violation"] is False

        def count(**params: Any) -> int:
            return client.get(f"{AI}/analyses", params).json()["count"]

        assert count(min_score=90) == 0 and count(max_score=90) == 1
        assert count(violations=1) == 0
        assert count(search="901112233") == 1 and count(search="555") == 0
        assert count(employees=str(analysis.call.operator_id)) == 1
        assert count(employees="999999") == 0
        assert count(date_from="2000-01-01", date_to="2000-01-02") == 0
        assert count(date_from="2000-01-01", date_to="2999-01-01") == 1
        assert client.get(f"{AI}/analyses", {"min_score": "x"}).status_code == 400

    def test_detail(self, client: APIClient, analysis: CallAnalysis) -> None:
        body = client.get(f"{AI}/analyses/{analysis.pk}").json()["analysis"]
        assert body["conversation_text"].startswith("Agent:")
        assert body["prompt_scores"][0] == {
            "key": "greeting_score",
            "name": "Greeting 10",
            "score": 10.0,
            "comment_html": "<div><b>Introduced</b> 10 / 10</div>",
            "is_violation": False,
        }
        assert body["client_data"]["answers"][0]["value"] is True
        assert body["call"] == {
            "id": analysis.call_id,
            "duration": 65,
            "direction": "inbound",
            "has_audio": True,
        }
        assert body["signature_verified"] is False
        assert "audio_file_url" not in json.dumps(body) and "secret.wav" not in json.dumps(body)

    def test_calls_list_and_detail_carry_ai(
        self,
        client: APIClient,
        analysis: CallAnalysis,
        call: CallRecord,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from apps.api import storage

        monkeypatch.setattr(storage, "presigned_url", lambda key: f"https://s3.test/{key}")
        row = client.get("/api/web/v1/calls").json()["results"][0]
        assert row["ai"] == {"analysis_id": analysis.pk, "final_score": 85.0}
        detail = client.get(f"/api/web/v1/calls/{call.pk}").json()["call"]
        assert detail["ai"] == {"analysis_id": analysis.pk, "final_score": 85.0}

    def test_calls_without_analysis_have_null_ai(self, client: APIClient, call: CallRecord) -> None:
        assert client.get("/api/web/v1/calls").json()["results"][0]["ai"] is None

    def test_operator_sees_only_own_calls(
        self,
        analysis: CallAnalysis,
        operator_user: User,
        company: Company,
        kotib: CrmIntegration,
    ) -> None:
        api = APIClient()
        api.force_authenticate(user=operator_user)
        assert api.get(f"{AI}/analyses").json()["count"] == 1
        assert api.get(f"{AI}/analyses/{analysis.pk}").status_code == 200
        assert api.get(f"{AI}/status").json()["is_admin"] is False

        other_user = User.objects.create_user(username="op-2@integr-co", company=company)
        OperatorProfile.all_objects.create(company=company, user=other_user, user_name="op-2")
        api.force_authenticate(user=other_user)
        assert api.get(f"{AI}/analyses").json()["count"] == 0
        assert api.get(f"{AI}/analyses/{analysis.pk}").status_code == 404

    def test_other_tenant_cannot_see(self, analysis: CallAnalysis) -> None:
        other = Company.objects.create(name="Other", slug="other-co", status="active")
        admin = User.objects.create_user(
            username="boss@other", email="boss@other", company=other, is_company_admin=True
        )
        api = APIClient()
        api.force_authenticate(user=admin)
        assert api.get(f"{AI}/analyses").json()["count"] == 0
        assert api.get(f"{AI}/analyses/{analysis.pk}").status_code == 404


class TestKotibCardSettings:
    def _kotib_card(self, client: APIClient) -> dict[str, Any]:
        rows = client.get(SETTINGS).json()["integrations"]
        return next(r for r in rows if r["provider"] == "kotib")["config"]

    def test_card_shows_url_and_stats(
        self, client: APIClient, analysis: CallAnalysis, kotib: CrmIntegration, settings: Any
    ) -> None:
        card = self._kotib_card(client)
        token = kotib.config["analysis_token"]
        assert card["analysis_webhook_url"].endswith(
            f".{settings.DOMAIN_ROOT}/api/public/kotib/analysis/{token}"
        )
        assert card["analysis_webhook_url"].split("://")[1].startswith("integr-co.")
        assert card["analysis_secret"] == ""
        assert card["analysis_count"] == 1 and card["analysis_last_received_at"]

    def test_token_created_lazily_for_old_rows(
        self, client: APIClient, kotib: CrmIntegration
    ) -> None:
        kotib.config = {k: v for k, v in kotib.config.items() if k != "analysis_token"}
        kotib.save()
        card = self._kotib_card(client)
        kotib.refresh_from_db()
        assert kotib.config["analysis_token"] in card["analysis_webhook_url"]

    def test_save_secret_and_rotate(
        self, client: APIClient, kotib: CrmIntegration, call: CallRecord
    ) -> None:
        response = client.put(f"{SETTINGS}/kotib/analysis", {"secret": SECRET}, format="json")
        assert response.status_code == 200
        card = response.json()["integration"]["config"]
        assert card["analysis_secret"] and SECRET not in json.dumps(response.json())
        kotib.refresh_from_db()
        assert kotib.config["analysis_secret"] == SECRET
        # Masked echo keeps it; empty is refused.
        client.put(f"{SETTINGS}/kotib/analysis", {"secret": card["analysis_secret"]}, format="json")
        kotib.refresh_from_db()
        assert kotib.config["analysis_secret"] == SECRET
        assert (
            client.put(f"{SETTINGS}/kotib/analysis", {"secret": ""}, format="json").status_code
            == 400
        )

        old_url = _url(kotib)
        rotated = client.post(f"{SETTINGS}/kotib/analysis/rotate").json()["integration"]["config"]
        kotib.refresh_from_db()
        assert kotib.config["analysis_token"] in rotated["analysis_webhook_url"]
        raw = json.dumps(_payload(call)).encode()
        assert (
            APIClient()
            .generic("POST", old_url, raw.decode(), content_type="application/json")
            .status_code
            == 404
        )
        assert _send(kotib, _payload(call), secret=SECRET).status_code == 200

        actions = list(AuditLog.objects.values_list("action", "changes"))
        assert ("settings.kotib_analysis_secret_saved", {}) in actions
        assert SECRET not in json.dumps([c for _, c in actions])

    def test_settings_require_connected_kotib(self, client: APIClient) -> None:
        assert (
            client.put(f"{SETTINGS}/kotib/analysis", {"secret": "x"}, format="json").status_code
            == 400
        )
        assert client.post(f"{SETTINGS}/kotib/analysis/rotate").status_code == 400

    def test_disconnect_wipes_endpoint_keeps_analyses(
        self, client: APIClient, analysis: CallAnalysis, kotib: CrmIntegration, monkeypatch: Any
    ) -> None:
        from apps.integrations import providers

        monkeypatch.setattr(providers, "kotib_disconnect", lambda *a: None)
        url = _url(kotib)
        assert client.delete(f"{SETTINGS}/kotib").status_code == 200
        kotib.refresh_from_db()
        assert "analysis_token" not in kotib.config and "analysis_secret" not in kotib.config
        raw = json.dumps(_payload()).encode()
        assert (
            APIClient()
            .generic("POST", url, raw.decode(), content_type="application/json")
            .status_code
            == 404
        )
        assert CallAnalysis.all_objects.filter(pk=analysis.pk).exists()
        assert client.get(f"{AI}/analyses/{analysis.pk}").status_code == 200

    def test_resave_keeps_token_and_secret(
        self, client: APIClient, kotib: CrmIntegration, monkeypatch: Any
    ) -> None:
        from apps.integrations import providers

        kotib.config = {**kotib.config, "analysis_secret": SECRET}
        kotib.save()
        token = kotib.config["analysis_token"]
        monkeypatch.setattr(
            providers,
            "kotib_connect",
            lambda *a: {
                "company": "X",
                "webhook_url": "https://kotib.test/api/v1/integration/doocall/y/webhook",
                "employees": None,
            },
        )
        assert (
            client.put(f"{SETTINGS}/kotib", {"is_enabled": True}, format="json").status_code == 200
        )
        kotib.refresh_from_db()
        assert kotib.config["analysis_token"] == token
        assert kotib.config["analysis_secret"] == SECRET

    def test_first_connect_creates_token(
        self, client: APIClient, company: Company, monkeypatch: Any
    ) -> None:
        from apps.integrations import providers

        monkeypatch.setattr(
            providers,
            "kotib_connect",
            lambda *a: {
                "company": "X",
                "webhook_url": "https://kotib.test/api/v1/integration/doocall/y/webhook",
                "employees": None,
            },
        )
        response = client.put(
            f"{SETTINGS}/kotib",
            {"is_enabled": True, "config": {"api_key": "k" * 20}},
            format="json",
        )
        assert response.status_code == 200
        row = CrmIntegration.all_objects.get(company=company, provider="kotib")
        assert len(row.config["analysis_token"]) >= 40
        assert (
            row.config["analysis_token"]
            in response.json()["integration"]["config"]["analysis_webhook_url"]
        )
