"""
Django settings for the doocall (CallCloud) project — PHASE 1 (Scaffold).

Only project-level plumbing lives here: installed apps, database, cache,
Celery, MinIO and business-config env wiring. No domain models or API
endpoints yet (those arrive in later phases). Every tunable is read from the
environment; defaults mirror ``.env.example`` so the stack boots out of the box.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except (TypeError, ValueError):
        return default


# ── Core ──────────────────────────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

# ── Product domains (company subdomains: <slug>.DOMAIN_ROOT) ───────────────
DOMAIN_ROOT = env("DOMAIN_ROOT", "doocall.local")
DOMAIN_APP = env("DOMAIN_APP", "app.doocall.local")
DOMAIN_ADMIN = env("DOMAIN_ADMIN", "app.admin.doocall.local")
URL_SCHEME = env("URL_SCHEME", "http" if DEBUG else "https")
# nginx always sets X-Forwarded-Proto; needed so request.is_secure() is
# correct behind TLS-terminating tunnels/proxies (jprq, prod LB).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Every company gets <slug>.DOMAIN_ROOT — accept the whole wildcard.
if f".{DOMAIN_ROOT}" not in ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(f".{DOMAIN_ROOT}")
# Refresh cookie shared across subdomains (e.g. ".doocall.uz"); empty = host-only.
REFRESH_COOKIE_DOMAIN = env("COOKIE_DOMAIN", f".{DOMAIN_ROOT}") or None

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_celery_beat",
    "drf_spectacular",
    # Local
    "apps.core",
    "apps.companies",
    "apps.accounts",
    "apps.calls",
    "apps.billing",
    "apps.api",
    "apps.web",
    "apps.partners",
    "apps.integrations",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.TenantMiddleware",  # request-scoped tenant context
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "doocall.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "doocall.wsgi.application"
ASGI_APPLICATION = "doocall.asgi.application"

# ── Database (Postgres 16) ─────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "doocall"),
        "USER": env("POSTGRES_USER", "doocall"),
        "PASSWORD": env("POSTGRES_PASSWORD", "doocall"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
}

# ── Cache / Redis ──────────────────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ── Celery ─────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = env("TZ", "Asia/Tashkent")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Beat entries — DatabaseScheduler syncs these into PeriodicTask on startup.
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "suspend-expired-trials": {
        "task": "apps.billing.tasks.suspend_expired_trials",
        "schedule": crontab(hour=0, minute=15),  # nightly
    },
    "generate-due-invoices": {
        "task": "apps.billing.tasks.generate_due_invoices",
        "schedule": crontab(hour=1, minute=0),  # daily period-end sweep
    },
    "cleanup-expired-audio": {
        "task": "apps.billing.tasks.cleanup_expired_audio",
        "schedule": crontab(hour=2, minute=0),  # stub until Phase 9
    },
    "accrue-daily-charges": {
        "task": "apps.billing.tasks.accrue_daily_charges",
        "schedule": crontab(hour=0, minute=30),  # bills the finished day
    },
    "settle-monthly-statements": {
        "task": "apps.billing.tasks.settle_monthly_statements",
        "schedule": crontab(hour=0, minute=45),  # no-op except on the 1st
    },
    "enforce-overdue-payments": {
        "task": "apps.billing.tasks.enforce_overdue_payments",
        "schedule": crontab(hour=1, minute=15),  # grace over → block access
    },
}

# ── Object storage (MinIO / S3-compatible) ─────────────────────────────────
MINIO_ENDPOINT = env("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", env("MINIO_ROOT_USER", "minioadmin"))
MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", env("MINIO_ROOT_PASSWORD", "minioadmin"))
MINIO_BUCKET = env("MINIO_BUCKET", "doocall-recordings")
MINIO_USE_SSL = env_bool("MINIO_USE_SSL", False)
# Host embedded in presigned URLs handed to devices (dev: localhost:9000).
MINIO_PUBLIC_ENDPOINT = env("MINIO_PUBLIC_ENDPOINT", "")
# Scheme of PUBLIC presigned URLs (the tunnel/CDN may terminate TLS even
# though the in-cluster MinIO connection stays plain http).
MINIO_PUBLIC_USE_SSL = env_bool("MINIO_PUBLIC_USE_SSL", MINIO_USE_SSL)

# ── DRF ────────────────────────────────────────────────────────────────────
REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.api.errors.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        # Per-scope device-API rates; generous for normal sync bursts
        # (§5.1: one upload per record, 300-500ms apart).
        "auth": env("THROTTLE_AUTH", "30/min"),
        "upload": env("THROTTLE_UPLOAD", "300/min"),
        "calls_list": env("THROTTLE_CALLS_LIST", "60/min"),
        "stats": env("THROTTLE_STATS", "60/min"),
        "log": env("THROTTLE_LOG", "10/min"),
        "public_api": env("THROTTLE_PUBLIC_API", "120/min"),
    },
}

# ── SimpleJWT (web cabinet auth) ───────────────────────────────────────────
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "SIGNING_KEY": env("JWT_SECRET_KEY", "") or SECRET_KEY,
    "ALGORITHM": env("JWT_ALGORITHM", "HS256"),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_TTL_MIN", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_TTL_DAYS", 30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Web views authenticate via SimpleJWT access tokens.
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "rest_framework_simplejwt.authentication.JWTAuthentication",
]

# ── Security hardening (Phase 9) ───────────────────────────────────────────
# Argon2 first: all new/updated passwords use argon2id.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# CORS: the three product domains + every company subdomain.
_CORS_HOSTS = (DOMAIN_ROOT, DOMAIN_APP, DOMAIN_ADMIN)
CORS_ALLOWED_ORIGINS = [
    origin for host in _CORS_HOSTS for origin in (f"https://{host}", f"http://{host}")
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    rf"^https?://[a-z0-9-]+\.{DOMAIN_ROOT.replace('.', chr(92) + '.')}$",
]
if DEBUG:
    CORS_ALLOWED_ORIGINS += ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS_ALLOW_CREDENTIALS = True

# Presigned audio URLs: ≤ 1 hour (Phase 9 security pass).
AUDIO_PRESIGN_EXPIRY_SECONDS = env_int("AUDIO_PRESIGN_EXPIRY_SECONDS", 3600)

# Audio retention (days) — global default; per-company override on Company.
AUDIO_RETENTION_DAYS = env_int("AUDIO_RETENTION_DAYS", 30)

# Structured JSON logging (prod) — human console in DEBUG.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "console": {"format": "%(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "console" if DEBUG else "json",
        },
    },
    "root": {"handlers": ["default"], "level": env("LOG_LEVEL", "INFO")},
}

# Sentry — enabled only when SENTRY_DSN is set.
SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:  # pragma: no cover - external service wiring
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=float(env("SENTRY_TRACES_RATE", "0.05")),
        send_default_pii=False,
    )

# Public pricing endpoint cache TTL (seconds).
PUBLIC_PRICING_CACHE_SECONDS = env_int("PUBLIC_PRICING_CACHE_SECONDS", 60)

# ── Feature flags ──────────────────────────────────────────────────────────
EMAIL_VERIFICATION_ENABLED = env_bool("EMAIL_VERIFICATION_ENABLED", False)

# ── Payment gateways (env-driven; sandbox-shaped adapters) ─────────────────
PAYME_MERCHANT_ID = env("PAYME_MERCHANT_ID", "")
PAYME_SECRET_KEY = env("PAYME_SECRET_KEY", "")
PAYME_ENDPOINT = env("PAYME_ENDPOINT", "https://checkout.paycom.uz")
CLICK_MERCHANT_ID = env("CLICK_MERCHANT_ID", "")
CLICK_SERVICE_ID = env("CLICK_SERVICE_ID", "")
CLICK_SECRET_KEY = env("CLICK_SECRET_KEY", "")
CLICK_ENDPOINT = env("CLICK_ENDPOINT", "https://api.click.uz/v2")

SPECTACULAR_SETTINGS = {
    "TITLE": "dooCall Mobile API",
    "DESCRIPTION": "Call-recording device API — contract per docs/backend-api-docs.md "
    "(§1 conventions: POST-only, JSON body auth, §9 error envelope).",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ── Email (Mailhog in dev) ─────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "mailhog")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@doocall.local")

# ── Business config (values pinned by master spec §10 — placeholders here) ──
TRIAL_DAYS = env_int("TRIAL_DAYS", 14)
DEFAULT_PRICE_PER_OPERATOR_UZS = env_int("DEFAULT_PRICE_PER_OPERATOR_UZS", 50000)
AUDIO_MAX_MB = env_int("AUDIO_MAX_MB", 20)

# ── Domains ────────────────────────────────────────────────────────────────
DOMAIN_ROOT = env("DOMAIN_ROOT", "localhost")
DOMAIN_APP = env("DOMAIN_APP", "app.localhost")
DOMAIN_ADMIN = env("DOMAIN_ADMIN", "app.admin.localhost")

# The configured domains are always allowed — prod needs only DOMAIN_* set.
for _domain in (DOMAIN_ROOT, DOMAIN_APP, DOMAIN_ADMIN):
    if _domain and _domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_domain)

# ── i18n / tz ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TZ", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True

# ── Static ─────────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
