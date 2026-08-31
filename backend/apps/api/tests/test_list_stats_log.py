"""§6 calls/list, §7 stats/summary, §8 log — contract tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.calls.models import AppLog, CallRecord

from .conftest import DOC_API_KEY

pytestmark = pytest.mark.django_db


def make_call(
    operator: OperatorProfile,
    call_id: str,
    *,
    call_type: str = "inbound",
    call_status: str = "answered",
    duration: int = 60,
) -> CallRecord:
    return CallRecord.all_objects.create(
        company=operator.company,
        operator=operator,
        call_id=call_id,
        call_type=call_type,
        call_status=call_status,
        from_number="+998901234567",
        to_number="+998998887766",
        counterparty_number="+998901234567",
        duration=duration,
        start_time=timezone.now() - timedelta(hours=1),
    )


class TestCallsList:
    URL = "/api/call/v1/calls/list"

    def test_mixed_exists_and_not(self, client: APIClient, operator: OperatorProfile) -> None:
        record = make_call(operator, "a1b2c3-...")

        # §6 literal request shape.
        response = client.post(
            self.URL,
            {
                "user_name": "operator1",
                "api_key": DOC_API_KEY,
                "call_ids": ["a1b2c3-...", "d4e5f6-..."],
            },
            format="json",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # §6 example: server_id present ONLY on exists=true entries.
        assert body["calls"] == [
            {
                "call_id": "a1b2c3-...",
                "exists": True,
                "server_id": f"srv_{record.server_id.hex}",
            },
            {"call_id": "d4e5f6-...", "exists": False},
        ]

    def test_other_companys_call_is_invisible(
        self, client: APIClient, operator: OperatorProfile
    ) -> None:
        from apps.accounts.models import User
        from apps.companies.models import Company

        other = Company.objects.create(name="Other", slug="other")
        other_user = User.objects.create_user(username="other-op", company=other)
        other_op = OperatorProfile.all_objects.create(
            company=other, user=other_user, user_name="other-op"
        )
        make_call(other_op, "foreign-1")

        response = client.post(
            self.URL,
            {"user_name": "operator1", "api_key": DOC_API_KEY, "call_ids": ["foreign-1"]},
            format="json",
        )
        assert response.json()["calls"] == [{"call_id": "foreign-1", "exists": False}]

    def test_empty_list_ok(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            self.URL,
            {"user_name": "operator1", "api_key": DOC_API_KEY, "call_ids": []},
            format="json",
        )
        assert response.status_code == 200
        assert response.json() == {"success": True, "calls": []}


class TestStatsSummary:
    URL = "/api/call/v1/stats/summary"

    def test_math_against_fixtures(self, client: APIClient, operator: OperatorProfile) -> None:
        make_call(operator, "c1", call_type="inbound", call_status="answered", duration=100)
        make_call(operator, "c2", call_type="inbound", call_status="no_answer", duration=0)
        make_call(operator, "c3", call_type="outbound", call_status="answered", duration=250)
        make_call(operator, "c4", call_type="outbound", call_status="no_answer", duration=0)
        make_call(operator, "c5", call_type="inbound", call_status="answered", duration=62)

        response = client.post(
            self.URL, {"user_name": "operator1", "api_key": DOC_API_KEY}, format="json"
        )

        assert response.status_code == 200
        # §7 — exact field set and values.
        assert response.json() == {
            "success": True,
            "total_duration_sec": 412,
            "total_count": 5,
            "inbound_count": 3,
            "outbound_count": 2,
            "missed_count": 2,
        }

    def test_zero_state(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            self.URL, {"user_name": "operator1", "api_key": DOC_API_KEY}, format="json"
        )
        assert response.json() == {
            "success": True,
            "total_duration_sec": 0,
            "total_count": 0,
            "inbound_count": 0,
            "outbound_count": 0,
            "missed_count": 0,
        }


class TestLog:
    URL = "/api/call/v1/log"

    # §8 literal log lines.
    LOG_TEXT = (
        "2026-08-09 14:03:11.482  D/CallReceiver: onCallStateChanged: OFFHOOK\n"
        "2026-08-09 14:03:58.117  I/UploadWorker: ✅ Muvaffaqiyatli yuklandi: a1b2c3-..."
    )

    def test_log_stored(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            self.URL,
            {
                "user_name": "operator1",
                "api_key": DOC_API_KEY,
                "hours": 24,
                "log_text": self.LOG_TEXT,
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"success": True}  # §8 exact body

        entry = AppLog.all_objects.get(operator=operator)
        assert entry.hours == 24
        assert entry.log_text == self.LOG_TEXT
        assert entry.company_id == operator.company_id

    def test_missing_log_text_400(self, client: APIClient, operator: OperatorProfile) -> None:
        response = client.post(
            self.URL,
            {"user_name": "operator1", "api_key": DOC_API_KEY, "hours": 24},
            format="json",
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "MISSING_FIELD"
