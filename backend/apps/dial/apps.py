from django.apps import AppConfig


class DialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dial"
    label = "dial"

    def ready(self) -> None:
        from . import signals  # noqa: F401 - registers the revoke receivers
