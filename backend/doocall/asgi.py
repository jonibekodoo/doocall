"""ASGI config for the doocall project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doocall.settings")

application = get_asgi_application()
