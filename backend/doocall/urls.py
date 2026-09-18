"""Root URL configuration for the doocall project."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.integrations.views_public import (
    CrmLogoView,
    CustomApiView,
    IntegratorLogoView,
    OdooAppDownloadView,
    ProviderLogoView,
    PublicCrmCatalogView,
    RecordRedirectView,
    SalesLogoView,
)
from apps.web.views_public import (
    PublicAppDownloadView,
    PublicAppLatestView,
    PublicIntegratorApplyView,
    PublicIntegratorsView,
    PublicLegalView,
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
    # Sales-manager portal API.
    path("api/sales/v1/", include(("apps.partners.urls_sales", "sales"))),
    # Company public API (moizvonki-style single action endpoint).
    re_path(r"^api/v1/?$", CustomApiView.as_view(), name="public-api"),
    # Permanent recording link for CRMs (302 → presigned MinIO URL).
    path("api/public/rec/<str:rec_id>", RecordRedirectView.as_view(), name="public-rec"),
    path("api/public/crm-logo/<int:entry_id>", CrmLogoView.as_view(), name="public-crm-logo"),
    path(
        "api/public/integrator-logo/<int:integrator_id>",
        IntegratorLogoView.as_view(),
        name="public-integrator-logo",
    ),
    path(
        "api/public/sales-logo/<int:manager_id>",
        SalesLogoView.as_view(),
        name="public-sales-logo",
    ),
    path(
        "api/public/provider-logo/<str:provider>",
        ProviderLogoView.as_view(),
        name="public-provider-logo",
    ),
    re_path(
        r"^api/public/crm-catalog/?$",
        PublicCrmCatalogView.as_view(),
        name="public-crm-catalog",
    ),
    re_path(
        r"^api/public/odoo-app/?$",
        OdooAppDownloadView.as_view(),
        name="public-odoo-app",
    ),
    # Public landing endpoints (no auth).
    # Slash-optional: the Next dev proxy strips trailing slashes.
    re_path(r"^api/public/pricing/?$", PublicPricingView.as_view(), name="public-pricing"),
    re_path(
        r"^api/public/legal/(?P<kind>[a-z]+)/?$", PublicLegalView.as_view(), name="public-legal"
    ),
    re_path(r"^api/public/app/latest/?$", PublicAppLatestView.as_view(), name="public-app-latest"),
    re_path(
        r"^api/public/app/download/?$", PublicAppDownloadView.as_view(), name="public-app-download"
    ),
    re_path(
        r"^api/public/integrator-apply/?$",
        PublicIntegratorApplyView.as_view(),
        name="public-integrator-apply",
    ),
    re_path(
        r"^api/public/integrators/?$",
        PublicIntegratorsView.as_view(),
        name="public-integrators",
    ),
]

# OpenAPI schema + Swagger UI — development only. Never exposed in production
# (DEBUG=false): the schema would list every endpoint to the public internet.
if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]

handler500 = "apps.api.errors.server_error"
