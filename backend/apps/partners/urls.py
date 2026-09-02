from django.urls import path

from apps.integrations import views_catalog as C

from . import views_admin as A
from . import views_partner as P

admin_urlpatterns = [
    path("dashboard", A.AdminDashboardView.as_view()),
    path("companies", A.AdminCompaniesView.as_view()),
    path("companies/<int:company_id>", A.AdminCompanyDetailView.as_view()),
    path("companies/<int:company_id>/reassign", A.AdminCompanyReassignView.as_view()),
    path(
        "companies/<int:company_id>/users/<int:user_id>/password",
        A.AdminCompanyUserPasswordView.as_view(),
    ),
    path("companies/<int:company_id>/<str:action>", A.AdminCompanyActionView.as_view()),
    path("payments", A.AdminPaymentsView.as_view()),
    path("payments/<int:payment_id>/approve", A.AdminPaymentApproveView.as_view()),
    path("payments/<int:payment_id>/refund", A.AdminPaymentRefundView.as_view()),
    path("settings/pricing", A.AdminPricingView.as_view()),
    path("integrators", A.AdminIntegratorsView.as_view()),
    path("integrators/<int:integrator_id>", A.AdminIntegratorDetailView.as_view()),
    path("settings/cashback", A.AdminCashbackSettingsView.as_view()),
    path("admins", A.AdminPlatformAdminsView.as_view()),
    path("admins/<int:user_id>", A.AdminPlatformAdminDetailView.as_view()),
    path("payouts", A.AdminPayoutsView.as_view()),
    path("payouts/<int:payout_id>/<str:action>", A.AdminPayoutActionView.as_view()),
    path("crm-catalog", C.AdminCrmCatalogView.as_view()),
    path("crm-catalog/<int:entry_id>", C.AdminCrmCatalogDetailView.as_view()),
    path("app-releases", A.AdminAppReleasesView.as_view()),
    path("app-releases/<int:release_id>", A.AdminAppReleaseDeleteView.as_view()),
    path("audit", A.AdminAuditView.as_view()),
    path("impersonate/stop", A.AdminImpersonateStopView.as_view()),
    path("impersonate/<int:company_id>", A.AdminImpersonateView.as_view()),
]

partner_urlpatterns = [
    path("dashboard", P.PartnerDashboardView.as_view()),
    path("companies", P.PartnerCompaniesView.as_view()),
    path("companies/<int:company_id>", P.PartnerCompanyDetailView.as_view()),
    path("accruals", P.PartnerAccrualsView.as_view()),
    path("payouts", P.PartnerPayoutsView.as_view()),
    path("profile", P.PartnerProfileView.as_view()),
]
