from django.urls import path

from apps.integrations import views as integration_views

from . import (
    views,
    views_billing,
    views_calls,
    views_contacts,
    views_dashboard,
    views_reports,
    views_settings,
)

app_name = "web"

urlpatterns = [
    # ── §6.1 Dashboard ────────────────────────────────────────────────────
    path("dashboard", views_dashboard.DashboardView.as_view(), name="dashboard"),
    # ── §6.2 Calls ────────────────────────────────────────────────────────
    path("calls", views_calls.CallsListView.as_view(), name="calls"),
    path("calls/columns", views_calls.CallColumnsView.as_view(), name="call-columns"),
    path("calls/export", views_calls.CallExportView.as_view(), name="call-export"),
    path(
        "calls/export/<int:export_id>",
        views_calls.CallExportDetailView.as_view(),
        name="call-export-detail",
    ),
    path("calls/<int:call_id>", views_calls.CallDetailView.as_view(), name="call-detail"),
    # ── §6.3 Contacts ─────────────────────────────────────────────────────
    path("contacts", views_contacts.ContactsView.as_view(), name="contacts"),
    path(
        "contacts/<int:contact_id>",
        views_contacts.ContactDetailView.as_view(),
        name="contact-detail",
    ),
    path(
        "contacts/from-call/<int:call_id>",
        views_contacts.ContactFromCallView.as_view(),
        name="contact-from-call",
    ),
    # ── §6.4 Reports ──────────────────────────────────────────────────────
    path("reports/general", views_reports.GeneralReportView.as_view(), name="r-general"),
    path("reports/weekday-matrix", views_reports.WeekdayMatrixView.as_view(), name="r-weekday"),
    path("reports/period-counts", views_reports.PeriodCountsView.as_view(), name="r-period"),
    path("reports/per-employee", views_reports.PerEmployeeView.as_view(), name="r-employee"),
    path("reports/per-client", views_reports.PerClientView.as_view(), name="r-client"),
    path("reports/unanswered", views_reports.UnansweredReportView.as_view(), name="r-unanswered"),
    path("reports/last-contact", views_reports.LastContactView.as_view(), name="r-last-contact"),
    # ── §6.5 Settings ─────────────────────────────────────────────────────
    path("settings/groups", views_settings.GroupsView.as_view(), name="groups"),
    path(
        "settings/groups/<int:group_id>",
        views_settings.GroupDetailView.as_view(),
        name="group-detail",
    ),
    path("settings/users", views_settings.UsersView.as_view(), name="users"),
    path(
        "settings/users/<int:operator_id>",
        views_settings.UserDetailView.as_view(),
        name="user-detail",
    ),
    path(
        "settings/users/<int:operator_id>/rotate-key",
        views_settings.OperatorKeyRotateView.as_view(),
        name="user-rotate-key",
    ),
    path("settings/devices", views_settings.DevicesView.as_view(), name="devices"),
    path(
        "settings/devices/<int:device_id>",
        views_settings.DeviceDeleteView.as_view(),
        name="device-delete",
    ),
    path("settings/sims/<int:sim_id>", views_settings.SimCardView.as_view(), name="sim"),
    path("settings/account", views_settings.AccountSettingsView.as_view(), name="account"),
    path("settings/api-key", views_settings.ApiKeyView.as_view(), name="api-key"),
    path("settings/webhook", views_settings.WebhookSettingsView.as_view(), name="webhook"),
    path(
        "settings/webhook/test",
        views_settings.WebhookTestView.as_view(),
        name="webhook-test",
    ),
    path("settings/license", views_settings.LicenseView.as_view(), name="license"),
    path(
        "settings/integrations",
        integration_views.IntegrationsView.as_view(),
        name="integrations",
    ),
    path(
        "settings/integrations/catalog",
        integration_views.CrmCatalogListView.as_view(),
        name="integrations-catalog",
    ),
    path(
        "settings/integrations/<str:provider>",
        integration_views.IntegrationDetailView.as_view(),
        name="integration-detail",
    ),
    path(
        "settings/integrations/<str:provider>/test",
        integration_views.IntegrationTestView.as_view(),
        name="integration-test",
    ),
    path("auth/register", views.RegisterView.as_view(), name="register"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("auth/companies", views.CompaniesView.as_view(), name="companies"),
    path("auth/handoff", views.HandoffCreateView.as_view(), name="handoff"),
    path("auth/handoff/redeem", views.HandoffRedeemView.as_view(), name="handoff-redeem"),
    path(
        "auth/password-reset",
        views.PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "auth/password-reset/confirm",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("auth/verify-email", views.EmailVerifyView.as_view(), name="verify-email"),
    path("billing/status", views.BillingStatusView.as_view(), name="billing-status"),
    path("billing/overview", views_billing.BillingOverviewView.as_view(), name="b-overview"),
    path("billing/pay", views_billing.BillingPayView.as_view(), name="b-pay"),
    path("billing/charges", views_billing.BillingChargesView.as_view(), name="b-charges"),
    path(
        "billing/statements",
        views_billing.BillingStatementsView.as_view(),
        name="b-statements",
    ),
    path("notifications", views_billing.NotificationsView.as_view(), name="notifications"),
    path(
        "notifications/read",
        views_billing.NotificationsReadView.as_view(),
        name="notifications-read",
    ),
    path(
        "billing/webhooks/<str:provider_name>",
        views.ProviderWebhookView.as_view(),
        name="billing-webhook",
    ),
]
