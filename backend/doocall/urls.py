"""Root URL configuration for the doocall project."""

from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.web.views_public import (
    PublicAppDownloadView,
    PublicAppLatestView,
    PublicPricingView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    # Mobile device API (contract §1: prefix api/call/v1/, POST-only).
    path("api/call/v1/", include("apps.api.urls")),
    # Web cabinet API (registration, JWT auth, billing).
    path("api/web/v1/", include("apps.web.urls")),
    # Admin portal API (platform staff).
    path("api/admin/v1/", include(("apps.partners.urls_admin", "padmin"))),
    # Partner portal API (integrators).
    path("api/partner/v1/", include(("apps.partners.urls_partner", "partner"))),
    # Public landing endpoints (no auth).
    # Slash-optional: the Next dev proxy strips trailing slashes.
    re_path(r"^api/public/pricing/?$", PublicPricingView.as_view(), name="public-pricing"),
    re_path(r"^api/public/app/latest/?$", PublicAppLatestView.as_view(), name="public-app-latest"),
    re_path(
        r"^api/public/app/download/?$", PublicAppDownloadView.as_view(), name="public-app-download"
    ),
    # OpenAPI schema + Swagger UI.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

handler500 = "apps.api.errors.server_error"
