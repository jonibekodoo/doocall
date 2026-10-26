"""ASGI config for the doocall project.

``doocall.asgi:application``: plain Django for http, plus the Remote Dial
device WebSocket (``/api/call/v1/ws``). The existing WSGI/gunicorn service
is unchanged; this entrypoint is meant for the separate ASGI "ws" service.
No Origin check: devices authenticate with an api_key frame (no cookies).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doocall.settings")

# Django must be set up before importing consumers (models).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.dial.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
