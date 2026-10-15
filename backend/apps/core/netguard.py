"""Outbound-request guard for customer-configured URLs (SSRF defence).

Company admins type CRM addresses (Bitrix24 webhook, amoCRM base URL, Odoo
URL) and every self-registered customer is a company admin, so these URLs
must never reach our own network:

* ``https`` only (``http`` allowed only with ``settings.DEBUG``), no
  ``user:pass@``, default/443 port only (any port with DEBUG);
* a real DNS name — no IP literals, no single-label names (Docker service
  names such as ``minio``), no ``localhost``/``.local``/``.internal`` and
  none of our own domains (``DOMAIN_ROOT`` and below);
* EVERY address the name resolves to must be public (``is_global``, not
  multicast; covers private, loopback, link-local incl. 169.254.169.254,
  CGNAT 100.64/10, reserved, unspecified, IPv6 ULA/link-local and
  IPv4-mapped private addresses).

:func:`open_url` re-checks right before the request and then connects to
the very address it checked (TLS SNI and ``Host`` keep the hostname), so a
DNS answer that changes between check and connect (rebinding) can't
redirect us. Redirects are never followed and environment proxies are
ignored. Residual risk: none known for the pinned path; the check on save is
advisory (DNS can change later) — the request-time check is the real gate.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa")


class UnsafeURL(ValueError):
    """The URL may not be called; ``str(exc)`` is a user-facing (uz) reason."""


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4 tunnelled in IPv6 (mapped, 6to4, Teredo) is judged by its IPv4.
        embedded = ip.ipv4_mapped or ip.sixtofour or (ip.teredo[1] if ip.teredo else None)
        if embedded is not None and not _ip_allowed(embedded):
            return False
    return ip.is_global and not ip.is_multicast


def _own_hosts() -> tuple[str, ...]:
    names = (
        getattr(settings, "DOMAIN_ROOT", ""),
        getattr(settings, "DOMAIN_APP", ""),
        getattr(settings, "DOMAIN_ADMIN", ""),
    )
    return tuple(n.lower() for n in names if n)


def resolve(host: str, port: int) -> list[str]:
    """All addresses of ``host`` (patched in tests)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def check_url(url: str) -> tuple[urllib.parse.SplitResult, str]:
    """Validate ``url``; returns the parsed URL and the vetted IP to use."""
    debug = bool(getattr(settings, "DEBUG", False))
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
        port = parts.port
    except ValueError:
        raise UnsafeURL("manzil noto'g'ri formatda") from None
    allowed_schemes = {"https", "http"} if debug else {"https"}
    if parts.scheme not in allowed_schemes:
        raise UnsafeURL("manzil https:// bilan boshlanishi kerak")
    if parts.username or parts.password or "@" in parts.netloc:
        raise UnsafeURL("manzilda login/parol bo'lmasligi kerak")
    if port not in (None, 443) and not debug:
        raise UnsafeURL("faqat standart (443) port ruxsat etiladi")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURL("manzilda domen yo'q")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeURL("IP manzil emas, domen nomini kiriting")
    if "." not in host or host == "localhost" or host.endswith(INTERNAL_SUFFIXES):
        raise UnsafeURL("ichki tarmoq nomi ruxsat etilmaydi — to'liq domen nomini kiriting")
    if any(host == own or host.endswith(f".{own}") for own in _own_hosts()):
        raise UnsafeURL("DooCall'ning o'z domeni ruxsat etilmaydi")
    try:
        addresses = resolve(host, port or (443 if parts.scheme == "https" else 80))
    except (OSError, UnicodeError):
        raise UnsafeURL("domen topilmadi (DNS)") from None
    if not addresses:
        raise UnsafeURL("domen topilmadi (DNS)")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            raise UnsafeURL("domen noto'g'ri manzilga yo'naltirilgan") from None
        if not _ip_allowed(ip):
            raise UnsafeURL("domen ichki (xususiy) tarmoq manziliga yo'naltirilgan")
    return parts, addresses[0]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """3xx is returned as an HTTPError instead of being followed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _pin(conn: http.client.HTTPConnection, ip: str) -> http.client.HTTPConnection:
    """Make ``conn`` open its TCP socket to ``ip`` (TLS/Host stay the name)."""

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        return socket.create_connection((ip, address[1]), *args, **kwargs)

    conn._create_connection = create_connection  # type: ignore[attr-defined]
    return conn


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, ip: str) -> None:
        super().__init__()
        self._ip = ip

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        def factory(host: str, **kwargs: Any) -> http.client.HTTPSConnection:
            conn = http.client.HTTPSConnection(host, **kwargs)
            _pin(conn, self._ip)
            return conn

        return self.do_open(factory, req, context=self._context)  # type: ignore[attr-defined]


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    """DEBUG-only plain HTTP, pinned the same way."""

    def __init__(self, ip: str) -> None:
        super().__init__()
        self._ip = ip

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        def factory(host: str, **kwargs: Any) -> http.client.HTTPConnection:
            return _pin(http.client.HTTPConnection(host, **kwargs), self._ip)

        return self.do_open(factory, req)


def open_url(request: urllib.request.Request, *, timeout: float) -> Any:
    """``urlopen`` for customer-configured URLs: check, pin, no redirects.

    Raises :class:`UnsafeURL` before any connection is made when the URL
    (or what its name resolves to now) is not allowed."""
    _, ip = check_url(request.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect,
        _PinnedHTTPSHandler(ip),
        _PinnedHTTPHandler(ip),
    )
    return opener.open(request, timeout=timeout)
