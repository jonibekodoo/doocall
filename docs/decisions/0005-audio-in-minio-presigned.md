# ADR-0005: Audio in MinIO, served via short-lived presigned URLs

**Status**: accepted (Phase 3, tightened Phase 9)

**Context**: Call audio is the bulk of data; the DB must stay lean; playback
must be access-controlled per company.

**Decision**: audio decodes from Base64 at upload and is stored in MinIO
under `<company>/<call_id>/<kind>/<filename>`; the API returns presigned GET
URLs generated against a public endpoint (`MINIO_PUBLIC_ENDPOINT`) with a TTL
of at most 1 hour (Phase-9 cap). Retention: a nightly Celery job deletes
audio older than the company's window (default 30 days) — CDR rows are kept.

**Consequences**: backend never streams bytes; URLs expire quickly; storage
cost is bounded by retention; deleting a company cascades rows while the
retention job owns object cleanup.
