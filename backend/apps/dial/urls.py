"""Remote Dial cabinet routes (included from apps/web/urls.py)."""

from django.urls import path

from . import views

urlpatterns = [
    path("dial", views.DialView.as_view(), name="dial"),
    path("dial/devices", views.DialDevicesView.as_view(), name="dial-devices"),
    path("dial/<uuid:command_id>", views.DialDetailView.as_view(), name="dial-detail"),
]
