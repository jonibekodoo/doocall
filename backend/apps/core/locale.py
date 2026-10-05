"""Request → interface language (uz / ru / en).

Order: explicit ``?lang=`` → the shared ``doocall_locale`` cookie set by the
frontend language switcher → ``Accept-Language`` → Uzbek (the default)."""

from __future__ import annotations

from typing import Any

LOCALES = ("uz", "ru", "en")


def request_locale(request: Any) -> str:
    explicit = (request.GET.get("lang") or "").lower()
    if explicit in LOCALES:
        return explicit
    cookie = (request.COOKIES.get("doocall_locale") or "").lower()
    if cookie in LOCALES:
        return cookie
    accept = (request.headers.get("Accept-Language") or "").lower()
    for loc in LOCALES:
        if accept.startswith(loc):
            return loc
    return "uz"
