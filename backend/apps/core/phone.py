"""Shared phone-number normalization — contract §1 (backend-api-docs.md).

The default (``phone_code="998"``) mirrors the device's
``RecordUploader.formatPhone()`` exactly:

* starts with ``+``  → returned unchanged (after separator cleanup);
* 9 digits          → prefixed with ``+998`` (local Uzbek subscriber number);
* 12 digits         → prefixed with ``+``;
* anything else     → returned as-is (cleaned) — the server must not guess.

Companies outside Uzbekistan carry their own ``Company.phone_code`` (country
calling code, digits only). For a code with a known national-number length
(``DIAL_CODES``) digits-only input becomes:

* national length               → ``+{code}{digits}``;
* ``{code}`` + national length  → ``+{digits}``;
* code ``7`` only: 11 digits starting with ``8`` (Russian/Kazakh trunk
  prefix) → ``+7`` + the last 10 digits;
* codes in ``TRUNK_ZERO`` only (TJ, KG): ``0`` + national length → the
  ``0`` is dropped. Uzbek numbers are not written with a trunk ``0``, so
  ``998`` deliberately does NOT get this rule (its behaviour is unchanged).

An unknown code (no national length on file) only keeps ``+…`` input — the
server never guesses a length.

Separators (spaces, dashes, dots, parentheses) are stripped before the rules
apply so ``"90 123-45-67"`` and ``"901234567"`` normalize identically.
"""

from __future__ import annotations

from typing import Any

_SEPARATORS = str.maketrans("", "", " -(). ")

DEFAULT_PHONE_CODE = "998"

# ISO 3166-1 alpha-2 → (calling code, national significant number length).
DIAL_CODES: dict[str, tuple[str, int]] = {
    "UZ": ("998", 9),
    "TJ": ("992", 9),
    "KG": ("996", 9),
    "KZ": ("7", 10),
    "RU": ("7", 10),
    "TM": ("993", 8),
    "AF": ("93", 9),
    "AZ": ("994", 9),
    "AM": ("374", 8),
    "GE": ("995", 9),
    "BY": ("375", 9),
    "UA": ("380", 9),
    "MD": ("373", 8),
    "TR": ("90", 10),
    "AE": ("971", 9),
    "CN": ("86", 11),
    "IN": ("91", 10),
    "PK": ("92", 10),
    "US": ("1", 10),
    "GB": ("44", 10),
}

# Calling code → national number length (one length per code above).
NATIONAL_LENGTH: dict[str, int] = dict(DIAL_CODES.values())

# Countries where a domestic leading "0" is common in typed numbers.
TRUNK_ZERO = frozenset({"992", "996"})


def phone_code_for_country(country: str | None) -> str | None:
    """Calling code for an ISO country, or None when we don't know it."""
    entry = DIAL_CODES.get((country or "").strip().upper())
    return entry[0] if entry else None


def company_phone_code(company: Any | None = None) -> str:
    """``Company.phone_code`` of ``company``, or of the ACTIVE TENANT when
    omitted (same contract as ``apps.core.tz.company_tz``)."""
    if company is None:
        from apps.companies.models import Company
        from apps.core.tenancy import get_current_company_id

        company_id = get_current_company_id()
        company = (
            Company.objects.filter(pk=company_id).only("phone_code").first() if company_id else None
        )
    return str(getattr(company, "phone_code", "") or DEFAULT_PHONE_CODE)


def normalize_phone(raw: str | None, phone_code: str = DEFAULT_PHONE_CODE) -> str:
    """Normalize ``raw`` to E.164-like form per contract §1, using
    ``phone_code`` as the default country calling code."""
    if not raw:
        return ""

    cleaned = raw.strip().translate(_SEPARATORS)
    if not cleaned:
        return ""

    if cleaned.startswith("+"):
        return cleaned

    if not cleaned.isdigit():
        return cleaned

    code = phone_code or DEFAULT_PHONE_CODE
    if code == DEFAULT_PHONE_CODE:
        # Device-mirror rules, unchanged (any 12 digits get a "+").
        if len(cleaned) == 9:
            return f"+998{cleaned}"
        if len(cleaned) == 12:
            return f"+{cleaned}"
        return cleaned

    national = NATIONAL_LENGTH.get(code)
    if national is None:
        return cleaned
    if len(cleaned) == national:
        return f"+{code}{cleaned}"
    if len(cleaned) == len(code) + national and cleaned.startswith(code):
        return f"+{cleaned}"
    if code == "7" and len(cleaned) == 11 and cleaned.startswith("8"):
        return f"+7{cleaned[1:]}"
    if code in TRUNK_ZERO and len(cleaned) == national + 1 and cleaned.startswith("0"):
        return f"+{code}{cleaned[1:]}"
    return cleaned
