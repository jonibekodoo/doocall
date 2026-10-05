#!/usr/bin/env bash
# dooCall — zero-downtime production deploy (blue-green per service).
#
#   scripts/deploy.sh                 # backend + frontend + celery
#   scripts/deploy.sh frontend        # only the listed services
#   scripts/deploy.sh backend celery
#
# Why: `docker compose up -d` stops the old container first and only then
# boots the new one (migrate + collectstatic + gunicorn ≈ 1 min of 502s).
# Here nothing is stopped until its replacement is proven healthy:
#
#   1. build the new images            (old containers keep serving)
#   2. apply migrations in a one-off   (must stay backward compatible —
#      container of the NEW image       the old code is still running)
#   3. per HTTP service: start a 2nd container next to the old one, wait
#      for its healthcheck + a smoke request, let nginx's resolver pick it
#      up, THEN stop the old one. If the new one never gets healthy it is
#      removed and the deploy aborts — users never notice.
#   4. celery worker/beat are simply recreated (no HTTP traffic).
#
# nginx must resolve upstreams dynamically (zone + resolver + `resolve`,
# see nginx/templates-server) — that is what lets two backends coexist and
# makes requests to a not-yet-listening peer fall through to the live one.
set -euo pipefail

cd "$(dirname "$0")/.."
C="docker compose -f docker-compose.prod.yml -f docker-compose.server.yml"
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}   # seconds to wait for a new container
DNS_SETTLE=${DNS_SETTLE:-12}            # > nginx `resolver … valid=10s`
BUILD_RETRIES=${BUILD_RETRIES:-3}

log() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
die() { printf '\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

targets=("$@")
[ ${#targets[@]} -eq 0 ] && targets=(backend frontend celery)
want() { local t; for t in "${targets[@]}"; do [ "$t" = "$1" ] && return 0; done; return 1; }

build_list=()
want backend  && build_list+=(backend)
want frontend && build_list+=(frontend)
want celery   && build_list+=(celery-worker celery-beat)
[ ${#build_list[@]} -eq 0 ] && die "nothing to deploy (use: backend frontend celery)"

# ── 1. build (retry on registry hiccups only) ────────────────────────────
log "Building: ${build_list[*]}"
attempt=1
until $C build "${build_list[@]}" > /tmp/doocall-build.log 2>&1; do
  if grep -qE "TLS handshake timeout|i/o timeout|registry-1\.docker\.io" /tmp/doocall-build.log \
     && [ "$attempt" -lt "$BUILD_RETRIES" ]; then
    echo "  registry timeout — retry $((attempt + 1))/$BUILD_RETRIES in 30s"
    attempt=$((attempt + 1)); sleep 30
  else
    grep -nE "Type error|error|Error|ERROR" -A6 /tmp/doocall-build.log | tail -40
    die "build failed (full log: /tmp/doocall-build.log) — nothing was changed"
  fi
done
echo "  build OK"

# ── 2. checks + migrations on the NEW image, old containers untouched ────
if want backend || want celery; then
  log "Django system check (new image)"
  $C run --rm -T --no-deps backend python manage.py check 2>&1 | tail -3 \
    || die "manage.py check failed — nothing was changed"
  log "Applying migrations (new image)"
  $C run --rm -T --no-deps backend python manage.py migrate --noinput 2>&1 | tail -4 \
    || die "migrate failed — old containers are still serving"
fi

# ── 3. blue-green swap of an HTTP service ────────────────────────────────
rollout() {
  local svc=$1 smoke=$2
  log "Rolling out $svc"
  local old new
  old=$($C ps -q "$svc")
  [ -n "$old" ] || { $C up -d --no-deps "$svc"; return; }   # first start

  $C up -d --no-deps --no-recreate --scale "$svc=2" "$svc" 2>&1 | tail -1
  new=$($C ps -q "$svc" | grep -vxF -e "$old" || true)
  new=$(echo "$new" | head -1)
  [ -n "$new" ] || die "$svc: no new container appeared"

  local waited=0 status=starting
  while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
    status=$(docker inspect --format '{{.State.Health.Status}}' "$new" 2>/dev/null || echo gone)
    [ "$status" = healthy ] && break
    [ "$status" = gone ] && break
    sleep 3; waited=$((waited + 3))
  done
  if [ "$status" != healthy ] || ! docker exec "$new" sh -c "$smoke" > /dev/null 2>&1; then
    echo "  new $svc container is not healthy ($status) — rolling back"
    docker logs --tail 25 "$new" 2>&1 | sed 's/^/    /' || true
    docker rm -f "$new" > /dev/null 2>&1 || true
    die "$svc rollout aborted; the old container never stopped serving"
  fi
  echo "  new container healthy after ${waited}s — letting nginx pick it up"
  sleep "$DNS_SETTLE"

  # Graceful: in-flight requests finish, nginx fails over to the new peer.
  # shellcheck disable=SC2086
  docker stop -t 30 $old > /dev/null && docker rm $old > /dev/null
  echo "  old container removed"
}

want backend  && rollout backend  'curl -fsS http://localhost:8000/healthz/'
want frontend && rollout frontend 'wget -qO- http://127.0.0.1:3000/login || node -e "fetch(\"http://127.0.0.1:3000/login\").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"'

# ── 4. background workers (no HTTP) ──────────────────────────────────────
if want celery; then
  log "Recreating celery worker + beat"
  $C up -d --no-deps celery-worker celery-beat 2>&1 | tail -2
fi

# ── 5. verify through nginx ──────────────────────────────────────────────
log "Verifying through nginx"
fail=0
for path in /healthz/ /login; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H 'Host: app.doocall.uz' \
         -H 'X-Forwarded-Proto: https' "http://127.0.0.1:8090$path" || echo 000)
  echo "  $path → $code"
  case "$code" in 2*|3*) ;; *) fail=1 ;; esac
done
[ "$fail" = 0 ] || die "post-deploy check failed"
$C ps --format '  {{.Service}}: {{.Status}}' backend frontend celery-worker celery-beat nginx
log "Deploy finished"
