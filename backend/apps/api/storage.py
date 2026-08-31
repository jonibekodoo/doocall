"""MinIO audio storage for /upload (contract §5.3/§5.4)."""

from __future__ import annotations

import io
import mimetypes
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from minio import Minio


def _presign_expiry() -> timedelta:
    # ≤1h per the Phase-9 security pass (env-tunable, never above 1h).
    seconds = min(int(getattr(settings, "AUDIO_PRESIGN_EXPIRY_SECONDS", 3600)), 3600)
    return timedelta(seconds=seconds)


@lru_cache(maxsize=1)
def client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


@lru_cache(maxsize=1)
def presign_client() -> Minio:
    """Client used ONLY for presigned URLs.

    Presigned URLs embed the endpoint host, so when devices live outside the
    compose network the URL must carry a publicly reachable host
    (``MINIO_PUBLIC_ENDPOINT``, e.g. ``localhost:9000`` in dev). Falls back to
    the internal endpoint when unset.
    """
    public = getattr(settings, "MINIO_PUBLIC_ENDPOINT", "")
    if not public or public == settings.MINIO_ENDPOINT:
        return client()
    return Minio(
        public,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_PUBLIC_USE_SSL,
        # Pin the region: the public host may be unreachable from inside
        # the compose network, and without it the SDK does a live
        # GetBucketLocation lookup before every presign.
        region="us-east-1",
    )


def ensure_bucket() -> None:
    if not client().bucket_exists(settings.MINIO_BUCKET):
        client().make_bucket(settings.MINIO_BUCKET)


def store_audio(object_key: str, payload: bytes, filename: str) -> str:
    """Upload audio bytes; returns a presigned GET URL (§5.4 ``audio.url``)."""
    ensure_bucket()
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    client().put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(payload),
        length=len(payload),
        content_type=content_type,
    )
    return presigned_url(object_key)


def presigned_url(object_key: str) -> str:
    return presign_client().presigned_get_object(
        settings.MINIO_BUCKET, object_key, expires=_presign_expiry()
    )
