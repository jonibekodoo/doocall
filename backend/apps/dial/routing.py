from django.urls import re_path

from .consumers import DeviceConsumer

websocket_urlpatterns = [
    # Hard-coded in the app (BuildConfig.WS_URL): wss://api.doocall.uz/api/call/v1/ws
    re_path(r"^api/call/v1/ws/?$", DeviceConsumer.as_asgi()),
]
