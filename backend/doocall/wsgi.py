"""WSGI config for the doocall project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doocall.settings")

application = get_wsgi_application()
