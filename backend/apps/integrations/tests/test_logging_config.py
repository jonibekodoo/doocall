"""The per-delivery Bitrix24 INFO line must reach the log in prod, where
celery runs with --loglevel=warning and hijacks the root logger."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]

SCRIPT = """
import logging
from types import SimpleNamespace

import django
django.setup()

from doocall.celery import app
# Exactly what `celery -A doocall worker --loglevel=warning` does to logging.
app.log.setup(loglevel="WARNING", redirect_stdouts=False)

from apps.integrations import providers
providers._b24_log_branch(
    SimpleNamespace(company_id=7, pk=42), "existing_entity", {"crm_mode": "classic"}
)
logging.getLogger("apps.web").info("NOISE-apps-web")
logging.getLogger().info("NOISE-root")
"""


def _run(**env: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed interpreter + inline script
        [sys.executable, "-c", SCRIPT],
        cwd=BACKEND,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "doocall.settings", **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout + result.stderr


@pytest.mark.parametrize("debug", ["True", "False"])
def test_branch_line_survives_celery_warning_root(debug: str) -> None:
    output = _run(LOG_LEVEL="WARNING", DEBUG=debug)
    line = next((row for row in output.splitlines() if "bitrix24 delivery" in row), None)
    assert line is not None, output
    assert "company=7 call=42 branch=existing_entity crm_mode=classic" in line
    # Django's LOGGING format (console in DEBUG, JSON otherwise), not Celery's.
    assert "INFO" in line and "apps.integrations.providers" in line
    if debug == "False":
        assert line.startswith("{") and '"levelname": "INFO"' in line
    # The rest stays quiet at the WARNING root level.
    assert "NOISE" not in output


def test_env_override_silences_it() -> None:
    output = _run(LOG_LEVEL="WARNING", INTEGRATIONS_LOG_LEVEL="WARNING")
    assert "bitrix24 delivery" not in output
