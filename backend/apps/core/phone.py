"""Shared phone-number normalization — contract §1 (backend-api-docs.md).

Mirrors the device's ``RecordUploader.formatPhone()`` exactly:

* starts with ``+``  → returned unchanged (after separator cleanup);
* 9 digits          → prefixed with ``+998`` (local Uzbek subscriber number);
* 12 digits         → prefixed with ``+``;
* anything else     → returned as-is (cleaned) — the server must not guess.

Separators (spaces, dashes, dots, parentheses) are stripped before the rules
apply so ``"90 123-45-67"`` and ``"901234567"`` normalize identically.
"""

from __future__ import annotations

_SEPARATORS = str.maketrans("", "", " -(). ")


def normalize_phone(raw: str | None) -> str:
    """Normalize ``raw`` to E.164-like form per contract §1."""
    if not raw:
        return ""

    cleaned = raw.strip().translate(_SEPARATORS)
    if not cleaned:
        return ""

    if cleaned.startswith("+"):
        return cleaned

    if cleaned.isdigit():
        if len(cleaned) == 9:
            return f"+998{cleaned}"
        if len(cleaned) == 12:
            return f"+{cleaned}"

    return cleaned
