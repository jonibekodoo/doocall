"""Company-subdomain helpers (MoiZvonki-style tenancy by host).

Every company gets ``<slug>.DOMAIN_ROOT`` (e.g. ``deepvision.doocall.uz``).
The cabinet UI and the mobile API are both served there; system hosts
(``DOMAIN_APP``, ``DOMAIN_ADMIN``, the bare root) are never company hosts.
"""

from __future__ import annotations

from django.conf import settings

RESERVED_SUBDOMAINS = {"www", "api", "app", "admin", "mail", "static", "cdn", "files", "console"}


def company_subdomain(host: str | None) -> str | None:
    """Return the company slug when ``host`` is ``<slug>.DOMAIN_ROOT``.

    Returns None for the root itself, the app/admin hosts, reserved or
    nested subdomains, and any host outside the product domain (test
    clients, health probes, direct container access).
    """
    host = (host or "").split(":")[0].strip().lower()
    root = getattr(settings, "DOMAIN_ROOT", "")
    if not host or not root or host == root:
        return None
    if host in (
        getattr(settings, "DOMAIN_APP", ""),
        getattr(settings, "DOMAIN_ADMIN", ""),
    ):
        return None
    suffix = f".{root}"
    if not host.endswith(suffix):
        return None
    sub = host[: -len(suffix)]
    if not sub or "." in sub or sub in RESERVED_SUBDOMAINS:
        return None
    return sub


def cabinet_url(slug: str) -> str:
    """Absolute URL of a company's cabinet on its own subdomain."""
    return f"{settings.URL_SCHEME}://{slug}.{settings.DOMAIN_ROOT}/cabinet"


def portal_url(portal: str) -> str:
    """Absolute URL of the admin/partner portal on the app host."""
    return f"{settings.URL_SCHEME}://{settings.DOMAIN_APP}/{portal}"


def cookie_domain_for(host: str | None) -> str | None:
    """REFRESH_COOKIE_DOMAIN only on product-domain hosts.

    Off-domain hosts (dev proxy localhost:3000, test clients) get a
    host-only cookie — browsers reject foreign Domain attributes anyway.
    """
    host = (host or "").split(":")[0].strip().lower()
    root = getattr(settings, "DOMAIN_ROOT", "")
    if root and (host == root or host.endswith(f".{root}")):
        return getattr(settings, "REFRESH_COOKIE_DOMAIN", None)
    return None


def _on_product_domain(host: str) -> bool:
    host = (host or "").split(":")[0].strip().lower()
    root = getattr(settings, "DOMAIN_ROOT", "")
    return bool(root) and (host == root or host.endswith(f".{root}"))


def cabinet_url_for(request, slug: str) -> str:  # type: ignore[no-untyped-def]
    """Cabinet URL appropriate for where the request came FROM.

    Product hosts get the company's own subdomain; foreign hosts (public
    tunnels like *.jprq.live have no wildcard subdomains) stay on the
    requesting host, where the cabinet is path-routed and neutral.
    """
    if _on_product_domain(request.get_host()):
        return cabinet_url(slug)
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}/cabinet"


def portal_url_for(request, portal: str) -> str:  # type: ignore[no-untyped-def]
    if _on_product_domain(request.get_host()):
        return portal_url(portal)
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}/{portal}"
