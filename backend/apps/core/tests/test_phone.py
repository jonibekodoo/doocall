"""Table-driven tests for contract §1 phone normalization."""

from __future__ import annotations

import pytest

from apps.core.phone import normalize_phone

CASES = [
    # (raw, expected, description)
    ("+998901234567", "+998901234567", "already E.164 — unchanged"),
    ("901234567", "+998901234567", "9 digits — +998 prefixed"),
    ("998901234567", "+998901234567", "12 digits — + prefixed"),
    ("+12025550123", "+12025550123", "foreign E.164 — unchanged"),
    ("90 123 45 67", "+998901234567", "9 digits with spaces"),
    ("90-123-45-67", "+998901234567", "9 digits with dashes"),
    ("(90) 123.45.67", "+998901234567", "9 digits with parens/dots"),
    ("+998 90 123-45-67", "+998901234567", "+ number with separators"),
    ("  901234567  ", "+998901234567", "leading/trailing whitespace"),
    ("12345678", "12345678", "8 digits — no rule matches, returned as-is"),
    ("1234567890", "1234567890", "10 digits — no rule matches"),
    ("4998901234567", "4998901234567", "13 digits — no rule matches"),
    ("", "", "empty string"),
    (None, "", "None"),
    ("abc123", "abc123", "non-numeric garbage passed through untouched"),
    ("998901234567 ", "+998901234567", "12 digits with trailing space"),
]


@pytest.mark.parametrize(("raw", "expected", "label"), CASES, ids=[c[2] for c in CASES])
def test_normalize_phone(raw: str | None, expected: str, label: str) -> None:
    assert normalize_phone(raw) == expected
