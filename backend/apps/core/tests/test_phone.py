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


CODE_CASES = [
    # (raw, phone_code, expected, description)
    ("901234567", "998", "+998901234567", "UZ default — same as no code"),
    ("0901234567", "998", "0901234567", "UZ — no trunk-0 rule (unchanged behaviour)"),
    ("921234567", "992", "+992921234567", "TJ 9 digits → +992"),
    ("92 123 45 67", "992", "+992921234567", "TJ with separators"),
    ("992921234567", "992", "+992921234567", "TJ already prefixed (12 digits)"),
    ("0921234567", "992", "+992921234567", "TJ trunk 0 dropped"),
    ("998901234567", "992", "998901234567", "TJ company, UZ digits w/o + — not guessed"),
    ("+998901234567", "992", "+998901234567", "'+' numbers are never rewritten"),
    ("555123456", "996", "+996555123456", "KG 9 digits → +996"),
    ("0555123456", "996", "+996555123456", "KG trunk 0 dropped"),
    ("7012345678", "7", "+77012345678", "KZ 10 digits → +7"),
    ("77012345678", "7", "+77012345678", "KZ 11 digits starting 7 → +"),
    ("87012345678", "7", "+77012345678", "KZ 11 digits starting 8 (trunk) → +7"),
    ("97012345678", "7", "97012345678", "KZ 11 digits other prefix — untouched"),
    ("12345678", "993", "+99312345678", "TM 8 digits → +993"),
    ("123456789", "49", "123456789", "unknown national length — untouched"),
    ("+4930123456", "49", "+4930123456", "unknown code keeps '+' input"),
    ("", "992", "", "empty"),
]


@pytest.mark.parametrize(
    ("raw", "code", "expected", "label"), CODE_CASES, ids=[c[3] for c in CODE_CASES]
)
def test_normalize_phone_per_company_code(raw: str, code: str, expected: str, label: str) -> None:
    assert normalize_phone(raw, code) == expected


def test_phone_code_for_country() -> None:
    from apps.core.phone import phone_code_for_country

    assert phone_code_for_country("TJ") == "992"
    assert phone_code_for_country("kz") == "7"
    assert phone_code_for_country("UZ") == "998"
    assert phone_code_for_country("ZZ") is None
    assert phone_code_for_country("") is None
