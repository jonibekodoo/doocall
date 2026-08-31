from django.urls import re_path

from . import views

app_name = "api"

# Contract paths carry no trailing slash (`/api/call/v1/auth`, §1); the
# optional `/?` tolerates clients that append one anyway (no APPEND_SLASH
# redirect on POST bodies).
urlpatterns = [
    re_path(r"^auth/?$", views.AuthView.as_view(), name="auth"),
    re_path(r"^upload/?$", views.UploadView.as_view(), name="upload"),
    re_path(r"^calls/list/?$", views.CallsListView.as_view(), name="calls-list"),
    re_path(r"^stats/summary/?$", views.StatsSummaryView.as_view(), name="stats-summary"),
    re_path(r"^log/?$", views.LogView.as_view(), name="log"),
]
