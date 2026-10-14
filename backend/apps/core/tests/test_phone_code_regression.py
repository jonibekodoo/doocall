"""UZ (default 998) normalization must match the pre-phone_code implementation
byte-for-byte, and the companies migration must map country → phone_code."""

from __future__ import annotations

import importlib
import random
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from django.apps import apps as django_apps

from apps.companies.models import Company
from apps.core.phone import normalize_phone

ROOT = Path(__file__).resolve().parents[3]


def _old_module() -> ModuleType | None:
    try:
        src = subprocess.run(
            ["git", "show", "main:backend/apps/core/phone.py"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        return None
    if "phone_code" in src:  # main already carries the new implementation
        return None
    mod = ModuleType("old_phone")
    exec(compile(src, "old_phone", "exec"), mod.__dict__)
    return mod


def test_uz_default_matches_legacy_implementation() -> None:
    old = _old_module()
    if old is None:
        pytest.skip("legacy phone.py unavailable on main")
    rnd = random.Random(7)
    samples = [None, "", " ", "+", "abc", "+998 90 123-45-67", "90 123-45-67", "(90) 1234567"]
    for n in range(0, 16):
        samples += ["".join(rnd.choice("0123456789") for _ in range(n)) for _ in range(30)]
        samples += ["+" + "".join(rnd.choice("0123456789") for _ in range(n)) for _ in range(5)]
    samples += ["8" + "9" * 11, "0" + "9" * 9, "998901234567", "901234567", "12ab34"]
    for s in samples:
        assert normalize_phone(s) == old.normalize_phone(s), s
        assert normalize_phone(s, "998") == old.normalize_phone(s), s
        assert normalize_phone(s, "") == old.normalize_phone(s), s


@pytest.mark.django_db
def test_migration_maps_country_to_phone_code() -> None:
    mig = importlib.import_module("apps.companies.migrations.0008_company_phone_code")
    rows = {"TJ": "992", "UZ": "998", "tj": "992", "": "998", "ZZ": "998", "KG": "996", "RU": "7"}
    made = {}
    for i, country in enumerate(rows):
        made[country] = Company.objects.create(name=f"c{i}", slug=f"c{i}", country=country)
        Company.objects.filter(pk=made[country].pk).update(phone_code="998")
    mig.set_from_country(django_apps, None)
    for country, expected in rows.items():
        made[country].refresh_from_db()
        assert made[country].phone_code == expected, country
