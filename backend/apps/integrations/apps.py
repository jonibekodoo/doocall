from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations"

    def ready(self) -> None:
        # Secret tokens in public webhook paths never reach our logs.
        from .logmask import install

        install()
