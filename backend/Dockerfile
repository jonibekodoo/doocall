# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is used by the compose healthcheck; libpq for psycopg runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching. Dev deps included so the same image
# runs the app AND the lint/test targets (Phase 1 keeps one image).
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000

# Default command is overridden per-service in docker-compose.
CMD ["gunicorn", "doocall.wsgi:application", "--bind", "0.0.0.0:8000"]
