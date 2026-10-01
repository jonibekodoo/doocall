from django.urls import path

from apps.integrations import views_catalog as C

from . import views_admin as A
from . import views_partner as P
from . import views_sales as S

admin_urlpatterns = [
    path("dashboard", A.AdminDashboardView.as_view()),
    path("dashboard/series", A.AdminDashboardSeriesView.as_view()),
    path("dashboard/calls-today", A.AdminCallsTodayView.as_view()),
    path("companies", A.AdminCompaniesView.as_view()),
    path("companies/<int:company_id>", A.AdminCompanyDetailView.as_view()),
    path("companies/<int:company_id>/reassign", A.AdminCompanyReassignView.as_view()),
    path(
        "companies/<int:company_id>/users/<int:user_id>/password",
        A.AdminCompanyUserPasswordView.as_view(),
    ),
    path("companies/<int:company_id>/<str:action>", A.AdminCompanyActionView.as_view()),
    path("payments", A.AdminPaymentsView.as_view()),
    path("payments/stats", A.AdminPaymentStatsView.as_view()),
    path("payments/<int:payment_id>/approve", A.AdminPaymentApproveView.as_view()),
    path("payments/<int:payment_id>/refund", A.AdminPaymentRefundView.as_view()),
    path("payments/<int:payment_id>/reject", A.AdminPaymentRejectView.as_view()),
    path("payments/<int:payment_id>", A.AdminPaymentDeleteView.as_view()),
    # Payment providers (on/off + logo) and the Paylov admin console.
    path("payment-providers", A.AdminPaymentProvidersView.as_view()),
    path("payment-providers/<str:provider>/logo", A.AdminPaymentProviderLogoView.as_view()),
    path("paylov/transactions", A.AdminPaylovTransactionsView.as_view()),
    path("paylov/transactions/<int:payment_id>/action", A.AdminPaylovTransactionActionView.as_view()),
    path("paylov/logs", A.AdminPaylovLogsView.as_view()),
    path("settings/pricing", A.AdminPricingView.as_view()),
    path("integrators", A.AdminIntegratorsView.as_view()),
    path("integrators/stats", A.AdminIntegratorStatsView.as_view()),
    path("integrator-applications", A.AdminIntegratorApplicationsView.as_view()),
    path(
        "integrator-applications/<int:application_id>",
        A.AdminIntegratorApplicationDetailView.as_view(),
    ),
    path(
        "integrators/<int:integrator_id>/password",
        A.AdminIntegratorPasswordView.as_view(),
    ),
    path(
        "integrators/<int:integrator_id>/logo",
        A.AdminIntegratorLogoView.as_view(),
    ),
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
    # Sales managers
    path("sales-managers", A.AdminSalesManagersView.as_view()),
    path("sales-managers/stats", A.AdminSalesManagerStatsView.as_view()),
    path("sales-managers/<int:manager_id>/password", A.AdminSalesManagerPasswordView.as_view()),
    path("sales-managers/<int:manager_id>/logo", A.AdminSalesManagerLogoView.as_view()),
    path("sales-managers/<int:manager_id>", A.AdminSalesManagerDetailView.as_view()),
    path("sales-payouts", A.AdminSalesPayoutsView.as_view()),
    path("sales-payouts/<int:payout_id>/<str:action>", A.AdminSalesPayoutActionView.as_view()),
    path("offer", A.AdminOfferView.as_view()),
    path("legal/<str:kind>", A.AdminLegalView.as_view()),
    # CRM (admin manages global funnels/stages + all leads/tasks)
    path("crm/pipelines", A.AdminPipelinesView.as_view()),
    path("crm/pipelines/<int:pipeline_id>", A.AdminPipelineDetailView.as_view()),
    path("crm/stages/<int:stage_id>", A.AdminStageDetailView.as_view()),
    path("leads", A.AdminLeadsView.as_view()),
    path("leads/<int:lead_id>", A.AdminLeadDetailView.as_view()),
    path("leads/<int:lead_id>/note", A.AdminLeadNoteView.as_view()),
    path("leads/<int:lead_id>/task", A.AdminLeadTaskView.as_view()),
    path("crm-tasks", A.AdminCrmTasksView.as_view()),
    path("crm-tasks/<int:task_id>", A.AdminCrmTaskDetailView.as_view()),
    path("crm/meta", A.AdminCrmMetaView.as_view()),
    path("crm/meta/<str:kind>/<int:item_id>", A.AdminCrmMetaDeleteView.as_view()),
    path("crm/board-stats", A.AdminBoardStatsView.as_view()),
]

sales_urlpatterns = [
    path("dashboard", S.SalesDashboardView.as_view()),
    path("integrators", S.SalesIntegratorsView.as_view()),
    path("integrators/<int:integrator_id>", S.SalesIntegratorDetailView.as_view()),
    path("payouts", S.SalesPayoutsView.as_view()),
    path("profile", S.SalesProfileView.as_view()),
    path("logo", S.SalesLogoView.as_view()),
    path("notifications", S.SalesNotificationsView.as_view()),
    # CRM (funnels are read-only for sales managers; admin manages them)
    path("crm/meta", S.SalesCrmMetaView.as_view()),
    path("crm/board-stats", S.SalesBoardStatsView.as_view()),
    path("pipelines", S.SalesPipelinesView.as_view()),
    path("leads", S.SalesLeadsView.as_view()),
    path("leads/<int:lead_id>", S.SalesLeadDetailView.as_view()),
    path("leads/<int:lead_id>/note", S.SalesLeadNoteView.as_view()),
    path("leads/<int:lead_id>/task", S.SalesLeadTaskView.as_view()),
    path("tasks", S.SalesTasksView.as_view()),
    path("tasks/<int:task_id>", S.SalesTaskDetailView.as_view()),
]

partner_urlpatterns = [
    path("dashboard", P.PartnerDashboardView.as_view()),
    path("companies", P.PartnerCompaniesView.as_view()),
    path("companies/<int:company_id>", P.PartnerCompanyDetailView.as_view()),
    path("accruals", P.PartnerAccrualsView.as_view()),
    path("payouts", P.PartnerPayoutsView.as_view()),
    path("profile", P.PartnerProfileView.as_view()),
    path("logo", P.PartnerLogoView.as_view()),
]
