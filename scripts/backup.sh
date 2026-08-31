#!/usr/bin/env bash
# dooCall backup: Postgres dump + MinIO mirror.
# Cron example (docs/deployment.md): 0 3 * * * /opt/doocall/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/doocall}"
STAMP="$(date +%Y%m%d-%H%M%S)"
COMPOSE="docker compose -f docker-compose.prod.yml"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR/pg" "$BACKUP_DIR/minio"

# 1. Postgres logical dump (custom format → parallel restore with pg_restore).
$COMPOSE exec -T db pg_dump -U "${POSTGRES_USER:-doocall}" -Fc "${POSTGRES_DB:-doocall}" \
  > "$BACKUP_DIR/pg/doocall-$STAMP.dump"

# 2. MinIO mirror (incremental; --remove keeps an exact replica).
$COMPOSE exec -T minio sh -c \
  "mc alias set local http://localhost:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null &&
   mc mirror --overwrite local/${MINIO_BUCKET:-doocall-recordings} /data-backup" || true
# When a host path is preferred, mount it and mirror there instead:
#   docker run --rm --network doocall-prod_default -v $BACKUP_DIR/minio:/backup minio/mc ...

# 3. Rotate old dumps.
find "$BACKUP_DIR/pg" -name '*.dump' -mtime "+$KEEP_DAYS" -delete

echo "backup complete: $BACKUP_DIR/pg/doocall-$STAMP.dump"
