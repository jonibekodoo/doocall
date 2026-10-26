#!/usr/bin/env bash
# dooCall — zero-downtime production deploy (blue-green per service).
#
#   scripts/deploy.sh                 # backend + ws + frontend + celery + nginx
#   scripts/deploy.sh frontend        # only the listed services
#   scripts/deploy.sh backend ws celery
#   scripts/deploy.sh nginx           # re-render templates + graceful reload only
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
#      `ws` (Remote Dial WebSockets) rolls the same way; when the old one
#      stops, uvicorn closes its sockets (1012) and phones reconnect — with
#      backoff — to the new container. No device needs to be connected for
#      the smoke check (it only expects the upgrade to be answered).
#   4. celery worker/beat are simply recreated (no HTTP traffic).
#   5. nginx re-renders its templates and reloads gracefully (nginx -t
#      first; on failure the previous config is restored, nothing reloads).
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
DOMAIN_ROOT=${DOMAIN_ROOT:-$(sed -n 's/^DOMAIN_ROOT=//p' .env 2>/dev/null | tail -1 | tr -d "\"'\r")}
WS_HOST=${WS_HOST:-api.${DOMAIN_ROOT:-doocall.uz}}   # host the phones dial
WS_PATH=/api/call/v1/ws

log() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }
die() { printf '\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

targets=("$@")
[ ${#targets[@]} -eq 0 ] && targets=(backend ws frontend celery nginx)
want() { local t; for t in "${targets[@]}"; do [ "$t" = "$1" ] && return 0; done; return 1; }

build_list=()
want backend  && build_list+=(backend)
want ws       && build_list+=(ws)
want frontend && build_list+=(frontend)
want celery   && build_list+=(celery-worker celery-beat)
for t in "${targets[@]}"; do
  case "$t" in backend|ws|frontend|celery|nginx) ;;
    *) die "unknown target '$t' (use: backend ws frontend celery nginx)" ;; esac
done

# WebSocket upgrade probe: prints the HTTP status. 101 = upgraded; 401/403 =
# the ws app answered but refused an anonymous socket — both prove the route
# reaches uvicorn. A 101 keeps the socket open, so curl ends on --max-time.
ws_probe() {  # ws_probe <base-url> [curl args…]
  local base=$1; shift
  curl -s -o /dev/null -w '%{http_code}' --http1.1 --max-time 3 \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
    -H 'Sec-WebSocket-Key: ZG9vY2FsbC13cy1wcm9iZQ==' "$@" "$base$WS_PATH" || true
}
WS_OK='^(101|401|403)$'

# ── 1. build (retry on registry hiccups only) ────────────────────────────
if [ ${#build_list[@]} -gt 0 ]; then
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
fi

# ── 2. checks + migrations on the NEW image, old containers untouched ────
# Run them from an image that was just rebuilt (all share ./backend): a
# ws-only or celery-only deploy must not migrate with a stale backend image.
mig_svc=""
want celery  && mig_svc=celery-worker
want ws      && mig_svc=ws
want backend && mig_svc=backend
if [ -n "$mig_svc" ]; then
  log "Django system check (new image: $mig_svc)"
  $C run --rm -T --no-deps "$mig_svc" python manage.py check 2>&1 | tail -3 \
    || die "manage.py check failed — nothing was changed"
  log "Applying migrations (new image: $mig_svc)"
  $C run --rm -T --no-deps "$mig_svc" python manage.py migrate --noinput 2>&1 | tail -4 \
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
# shellcheck disable=SC2016  # expanded by sh inside the container
want ws       && rollout ws 'curl -fsS http://localhost:8001/healthz/ >/dev/null && code=$(curl -s -o /dev/null -w "%{http_code}" --http1.1 --max-time 3 -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: ZG9vY2FsbC13cy1wcm9iZQ==" http://localhost:8001/api/call/v1/ws); case "$code" in 101|401|403) exit 0 ;; *) echo "ws upgrade answered $code" >&2; exit 1 ;; esac'
want frontend && rollout frontend 'wget -qO- http://127.0.0.1:3000/login || node -e "fetch(\"http://127.0.0.1:3000/login\").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"'

# ── 4. background workers (no HTTP) ──────────────────────────────────────
if want celery; then
  log "Recreating celery worker + beat"
  $C up -d --no-deps celery-worker celery-beat 2>&1 | tail -2
fi

# ── 5. nginx: re-render templates, test, reload (no dropped connections) ─
# Templates are only rendered when the container starts, so a changed
# route (e.g. the ws location) needs this. Keeps a copy of the live conf.d
# and restores it if `nginx -t` fails — the running nginx is never touched.
if want nginx; then
  log "Re-rendering nginx templates + graceful reload"
  # shellcheck disable=SC2016
  $C exec -T nginx sh -c '
    rm -rf /tmp/conf.d.prev && cp -a /etc/nginx/conf.d /tmp/conf.d.prev &&
    /docker-entrypoint.d/20-envsubst-on-templates.sh > /dev/null &&
    if nginx -t 2> /tmp/nginx-t.log; then
      nginx -s reload
    else
      cat /tmp/nginx-t.log >&2
      rm -rf /etc/nginx/conf.d/* && cp -a /tmp/conf.d.prev/. /etc/nginx/conf.d/
      exit 1
    fi' || die "nginx config test failed — previous config restored, nginx kept serving it"
  echo "  nginx reloaded"
fi

# ── 6. verify through nginx ──────────────────────────────────────────────
log "Verifying through nginx"
fail=0
for path in /healthz/ /login; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H 'Host: app.doocall.uz' \
         -H 'X-Forwarded-Proto: https' "http://127.0.0.1:8090$path" || echo 000)
  echo "  $path → $code"
  case "$code" in 2*|3*) ;; *) fail=1 ;; esac
done
if [ -n "$($C ps -q ws)" ]; then
  code=$(ws_probe http://127.0.0.1:8090 -H "Host: $WS_HOST" -H 'X-Forwarded-Proto: https')
  echo "  $WS_HOST$WS_PATH (WebSocket upgrade) → $code"
  if ! [[ "$code" =~ $WS_OK ]]; then
    fail=1
    echo "    expected 101/401/403 — is the nginx route live? (scripts/deploy.sh nginx)"
  fi
fi
[ "$fail" = 0 ] || die "post-deploy check failed"
$C ps --format '  {{.Service}}: {{.Status}}' backend ws frontend celery-worker celery-beat nginx
log "Deploy finished"
