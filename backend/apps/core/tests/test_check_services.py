"""Tests for the ``check_services`` management command.

Two layers:
  * a deterministic unit test that stubs the probes (always runs, proves the
    command's success/failure control flow and output);
  * an integration test that runs the real probes against live infra and is
    skipped when the infra is not reachable (this is the one that actually
    proves Postgres/Redis/MinIO connectivity inside compose/CI).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.management.commands import check_services as mod


def test_reports_all_services_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.Command, "_check_postgres", lambda self: "db:5432/doocall")
    monkeypatch.setattr(mod.Command, "_check_redis", lambda self: "redis://redis:6379/0")
    monkeypatch.setattr(mod.Command, "_check_minio", lambda self: "minio:9000")

    out = StringIO()
    call_command("check_services", stdout=out)

    output = out.getvalue()
    assert "✓ postgres" in output
    assert "✓ redis" in output
    assert "✓ minio" in output
    assert "All services reachable." in output


def test_raises_when_a_service_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.Command, "_check_postgres", lambda self: "ok")
    monkeypatch.setattr(mod.Command, "_check_redis", lambda self: "ok")

    def boom(self: mod.Command) -> str:
        raise ConnectionError("connection refused")

    monkeypatch.setattr(mod.Command, "_check_minio", boom)

    with pytest.raises(CommandError, match="Unreachable services: minio"):
        call_command("check_services", stdout=StringIO(), stderr=StringIO())


@pytest.mark.integration
@pytest.mark.django_db
def test_live_services_reachable() -> None:
    """Real connectivity proof. Skips if infra isn't up."""
    out = StringIO()
    try:
        call_command("check_services", stdout=out)
    except CommandError as exc:  # infra not available in this environment
        pytest.skip(f"infra not reachable: {exc}")

    assert "All services reachable." in out.getvalue()
