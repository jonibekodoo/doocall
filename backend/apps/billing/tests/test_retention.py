"""Audio retention job — frozen-time deletion with per-company override."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, User
from apps.api import storage
from apps.billing.tasks import cleanup_expired_audio, run_audio_retention
from apps.calls.models import CallAudio, CallRecord
from apps.companies.models import Company
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def removed_objects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    removed: list[str] = []

    class FakeClient:
        def remove_object(self, bucket: str, key: str) -> None:
            removed.append(key)

    monkeypatch.setattr(storage, "client", lambda: FakeClient())
    return removed


def make_audio(company: Company, call_id: str, *, age_days: int) -> CallAudio:
    user, _ = User.objects.get_or_create(
        username=f"ret-op@{company.slug}", defaults={"company": company}
    )
    operator, _ = OperatorProfile.all_objects.get_or_create(
        company=company, user=user, defaults={"user_name": f"ret-op-{company.slug}"}
    )
    record = CallRecord.all_objects.create(
        company=company,
        operator=operator,
        call_id=call_id,
        call_type="inbound",
        call_status="answered",
        from_number="+998901234567",
        to_number="+998998887766",
        counterparty_number="+998901234567",
        duration=30,
        start_time=timezone.now() - timedelta(days=age_days),
    )
    audio = CallAudio.objects.create(
        call=record,
        filename=f"{call_id}.ogg",
        object_key=f"{company.pk}/{call_id}/primary/{call_id}.ogg",
        size_bytes=100,
    )
    # created_at is auto_now_add — backdate it explicitly.
    CallAudio.objects.filter(pk=audio.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return audio


class TestAudioRetention:
    def test_deletes_only_beyond_default_window(
        self, company: Company, removed_objects: list[str]
    ) -> None:
        old = make_audio(company, "ret-old", age_days=45)  # > 30 default
        fresh = make_audio(company, "ret-fresh", age_days=5)

        frozen_now = timezone.now()
        deleted = run_audio_retention(frozen_now)

        assert deleted == 1
        assert not CallAudio.objects.filter(pk=old.pk).exists()
        assert CallAudio.objects.filter(pk=fresh.pk).exists()
        assert removed_objects == [old.object_key]
        # CDR itself untouched.
        assert CallRecord.all_objects.filter(call_id="ret-old").exists()
        assert AuditLog.objects.filter(company=company, action="audio.retention_cleanup").exists()

    def test_per_company_override_shortens_window(
        self, company: Company, removed_objects: list[str]
    ) -> None:
        company.audio_retention_days = 7  # admin-tunable
        company.save(update_fields=["audio_retention_days"])
        mid = make_audio(company, "ret-mid", age_days=10)  # >7, <30

        assert run_audio_retention(timezone.now()) == 1
        assert not CallAudio.objects.filter(pk=mid.pk).exists()

    def test_frozen_time_via_task_wrapper(
        self, company: Company, removed_objects: list[str]
    ) -> None:
        make_audio(company, "ret-frozen", age_days=20)  # fresh today…
        future = (timezone.now() + timedelta(days=15)).isoformat()  # …expired later

        assert cleanup_expired_audio(now_iso=future) == 1

    def test_survives_missing_minio_object(
        self, company: Company, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class ExplodingClient:
            def remove_object(self, bucket: str, key: str) -> None:
                raise RuntimeError("object gone")

        monkeypatch.setattr(storage, "client", lambda: ExplodingClient())
        make_audio(company, "ret-ghost", age_days=60)
        assert run_audio_retention(timezone.now()) == 1  # row still cleaned up


class TestOperatorKeyRotation:
    def test_admin_rotates_key_old_key_dies(self, company: Company) -> None:
        admin = User.objects.create_user(
            username="rot-admin@x", company=company, is_company_admin=True
        )
        op_user = User.objects.create_user(username="rot-op@x", company=company)
        profile = OperatorProfile.all_objects.create(
            company=company, user=op_user, user_name="rot-op", api_key="old-key-123"
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.post(f"/api/web/v1/settings/users/{profile.pk}/rotate-key")

        assert response.status_code == 200
        new_key = response.json()["api_key"]
        assert new_key != "old-key-123" and len(new_key) == 32

        # Old key rejected on the mobile API; new key works.
        mobile = APIClient()
        old = mobile.post(
            "/api/call/v1/stats/summary",
            {"user_name": "rot-op", "api_key": "old-key-123"},
            format="json",
        )
        assert old.status_code == 401
        fresh = mobile.post(
            "/api/call/v1/stats/summary",
            {"user_name": "rot-op", "api_key": new_key},
            format="json",
        )
        assert fresh.status_code == 200
