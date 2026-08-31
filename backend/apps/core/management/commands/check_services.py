"""``check_services`` — prove the backend can reach its infra dependencies.

Checks Postgres, Redis and MinIO in turn, prints a per-service line, and exits
non-zero (via :class:`CommandError`) if any dependency is unreachable. Used as a
readiness gate in compose/CI and covered by ``tests/test_check_services.py``.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Verify connectivity to Postgres, Redis and MinIO."

    def handle(self, *args: object, **options: object) -> None:
        checks: list[tuple[str, Callable[[], str]]] = [
            ("postgres", self._check_postgres),
            ("redis", self._check_redis),
            ("minio", self._check_minio),
        ]

        failures: list[str] = []
        for name, check in checks:
            try:
                detail = check()
            except Exception as exc:  # noqa: BLE001 - report any failure uniformly
                failures.append(name)
                self.stdout.write(self.style.ERROR(f"✗ {name}: {exc}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"✓ {name}: {detail}"))

        if failures:
            raise CommandError(f"Unreachable services: {', '.join(failures)}")

        self.stdout.write(self.style.SUCCESS("All services reachable."))

    # ── individual probes ──────────────────────────────────────────────────
    def _check_postgres(self) -> str:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db = settings.DATABASES["default"]
        return f"{db['HOST']}:{db['PORT']}/{db['NAME']}"

    def _check_redis(self) -> str:
        import redis  # local import keeps the command importable without redis

        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=5)
        client.ping()
        return settings.REDIS_URL

    def _check_minio(self) -> str:
        from minio import Minio

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        # list_buckets() performs an authenticated round-trip to the server.
        client.list_buckets()
        return settings.MINIO_ENDPOINT
