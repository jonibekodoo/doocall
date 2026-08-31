# dooCall — Production Deployment (doocall.uz)

Single host, Docker Compose (`docker-compose.prod.yml`): nginx (TLS,
host-routed) → Next.js standalone + gunicorn/Django → Postgres 16 /
Redis 7 / MinIO. Celery worker + beat for exports, webhooks, billing
sweeps and audio retention.

## 1. Server requirements

* Ubuntu 22.04/24.04 LTS (yoki istalgan systemd distro), **4 vCPU / 8 GB
  RAM / 100+ GB SSD** (audio MinIO'da o'sadi — diskni kuzating).
* Ochiq portlar: **80, 443** (5432/6379/9000 tashqariga chiqmaydi —
  compose ichki tarmog'ida qoladi).
* Docker + compose plugin:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # relogin
```

## 2. DNS (doocall.uz)

Registrator panelida quyidagi yozuvlarni yarating — **hammasi bitta
server IP'siga**:

| Turi | Nomi (host) | Qiymati | Nima uchun |
|---|---|---|---|
| A | `@` | SERVER_IP | landing — `doocall.uz` |
| A | `www` | SERVER_IP | `www.doocall.uz` → landing |
| A | `app` | SERVER_IP | portallar — kabinet/admin/partner |
| A | `admin` | SERVER_IP | Django admin (`admin.doocall.uz`) |
| A | `files` | SERVER_IP | MinIO presigned URL'lar (audio + APK) |
| **A** | **`*`** | SERVER_IP | **kompaniya subdomenlari** — `deepvision.doocall.uz`, `ahlan-house.doocall.uz`, … |

Wildcard (`*`) yozuvi majburiy: har yangi kompaniya ro'yxatdan o'tganda
DNS'ga tegmasdan o'z subdomeni ishlaydi. Aniq yozuvlar (`app`, `files`…)
wildcard'dan ustun turadi.

TTL: 300–3600s. Tekshirish: `dig +short app.doocall.uz` va
`dig +short anything.doocall.uz` — ikkalasi ham SERVER_IP qaytarsin.

## 3. TLS — bitta wildcard sertifikat

`*.doocall.uz` uchun **DNS-01 challenge** shart (http-01 wildcard
bermaydi):

```bash
sudo apt install -y certbot
sudo certbot certonly --manual --preferred-challenges dns \
  -d "doocall.uz" -d "*.doocall.uz"
# certbot ko'rsatgan TXT yozuvni DNS'ga qo'ying:
#   _acme-challenge.doocall.uz  TXT  <token>
# tarqalganini tekshiring:  dig +short TXT _acme-challenge.doocall.uz
```

Sertifikat: `/etc/letsencrypt/live/doocall.uz/{fullchain,privkey}.pem` —
prod nginx (`nginx/templates-prod/`) aynan shu yo'lni kutadi
(`DOMAIN_ROOT` bo'yicha).

**Yangilash (muhim):** `--manual` DNS-01 avtomatik yangilanmaydi (har 90
kunda TXT qo'lda). Avtomat uchun:

* **acme.sh + DNS API** — provayderingizda API bo'lsa:
  `acme.sh --issue --dns dns_<provider> -d doocall.uz -d '*.doocall.uz'`
* **Cloudflare NS** — domen NS'larini Cloudflare'ga o'tkazib,
  `certbot --dns-cloudflare` (eng oson avtomat yo'l).

Yangilangandan keyin:
`docker compose -f docker-compose.prod.yml restart nginx`.

## 4. .env — production qiymatlar

`cp .env.example .env` qilib, quyidagilarni ALBATTA o'zgartiring:

```dotenv
DEBUG=false
DJANGO_SECRET_KEY=<64+ belgi tasodifiy>          # openssl rand -hex 48
DJANGO_ALLOWED_HOSTS=doocall.uz,www.doocall.uz,app.doocall.uz,admin.doocall.uz,backend

# ── Domenlar ──
DOMAIN_ROOT=doocall.uz
DOMAIN_APP=app.doocall.uz
DOMAIN_ADMIN=admin.doocall.uz          # e'tibor: app.admin EMAS —
                                       # *.doocall.uz sertifikati faqat
                                       # BIR darajani qoplaydi
COOKIE_DOMAIN=.doocall.uz              # sessiya subdomenlar aro
URL_SCHEME=https

# ── Postgres/MinIO — kuchli parollar ──
POSTGRES_PASSWORD=<kuchli>
MINIO_ROOT_USER=<yangi nom>
MINIO_ROOT_PASSWORD=<kuchli>
MINIO_ACCESS_KEY=<MINIO_ROOT_USER bilan bir xil>
MINIO_SECRET_KEY=<MINIO_ROOT_PASSWORD bilan bir xil>

# ── MinIO public (presigned audio + APK) ──
MINIO_PUBLIC_ENDPOINT=files.doocall.uz
MINIO_PUBLIC_USE_SSL=true

# ── Email (parol tiklash, xabarlar) ──
EMAIL_HOST=<smtp>  EMAIL_HOST_USER=…  EMAIL_HOST_PASSWORD=…
EMAIL_USE_TLS=true  DEFAULT_FROM_EMAIL=no-reply@doocall.uz

# ── Payme/Click real merchant kredensiyallari ──
PAYME_MERCHANT_ID=…  PAYME_KEY=…  CLICK_MERCHANT_ID=…  CLICK_SECRET=…

# Mobil hujjat namunasi (§1 server maydoni)
NEXT_PUBLIC_API_BASE_URL=https://app.doocall.uz/api/call/v1
```

`DOMAIN_ROOT` o'rnatilishi bilan Django `.doocall.uz` wildcard'ini
ALLOWED_HOSTS'ga o'zi qo'shadi; CORS subdomenlarni regex bilan ochadi.

## 5. Ishga tushirish

```bash
git clone <repo> /opt/doocall && cd /opt/doocall     # yoki rsync
cp .env.example .env && nano .env                    # 4-bo'lim qiymatlari

docker compose -f docker-compose.prod.yml config -q  # validatsiya
docker compose -f docker-compose.prod.yml up -d --build
# backend o'zi migrate + collectstatic qiladi (compose commandida)

# birinchi ishga tushirishda:
docker compose -f docker-compose.prod.yml exec backend \
  python manage.py createsuperuser        # Django admin uchun
# demo ma'lumot kerak bo'lsa: … exec backend python manage.py seed_demo
```

Tekshirish:

```bash
curl -I https://doocall.uz/                      # 200 — landing
curl -I https://app.doocall.uz/login             # 200 — portallar
curl -I https://anything.doocall.uz/cabinet      # 200 — wildcard
curl -s https://doocall.uz/api/public/pricing    # jonli narx JSON
curl -s https://app.doocall.uz/healthz/          # {"status":"ok"}
```

## 6. Nginx topologiyasi (`nginx/templates-prod/`)

| Host | Nima |
|---|---|
| `doocall.uz`, `www.` | landing (+ `/api/public`, ro'yxatdan o'tish, APK tugmasi) |
| `app.doocall.uz` | `/cabinet` · `/admin` · `/partner` (path-routed portallar) |
| `admin.doocall.uz` | Django admin (barcha kompaniyalar) |
| `files.doocall.uz` | MinIO (presigned audio + APK; 9000-port tashqariga ochilmaydi) |
| `*.doocall.uz` | kompaniya kabineti + web/mobil API (host↔tenant guard) |
| `:80` | ACME webroot + hamma narsani https'ga 301 |

Mobil ilova qurilma sozlamasida `server` maydoniga kompaniyaning o'z
subdomenini yozadi: `https://<slug>.doocall.uz`.

jprq template'lari (`nginx/templates/jprq.conf.template`) faqat dev
uchun — prod `templates-prod/` dan o'qiydi, u yerda ular yo'q.

## 7. Zaxira nusxa (backup)

`scripts/backup.sh` — pg_dump (custom format) + MinIO mirror, 14 kunlik
rotatsiya. Cron:

```cron
0 3 * * * cd /opt/doocall && ./scripts/backup.sh >> /var/log/doocall-backup.log 2>&1
```

Restore:

```bash
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U doocall -d doocall --clean < backups/pg/doocall-<stamp>.dump
```

Zaxiralarni serverdan TASHQARIGA ko'chiring (rclone / ikkinchi host / s3).

## 8. Yangilash (deploy)

```bash
cd /opt/doocall && git pull
docker compose -f docker-compose.prod.yml up -d --build
# nginx konfiguratsiyasi o'zgargan bo'lsa:
docker compose -f docker-compose.prod.yml restart nginx
```

## 9. Scheduled jobs (celery-beat, Asia/Tashkent)

| 00:15 | trial-expiry suspension |
| 01:00 | invoice generation (period rollover) |
| 02:00 | audio retention cleanup (default 30 days, per-company override) |

## 10. Monitoring & security

* `SENTRY_DSN` env → backend errors + performance traces (5% sample).
* Structured JSON logs on stdout (`LOG_LEVEL`) — ship with any log driver.
* Healthchecks: every service defines one; `docker compose ps` is the
  first-line status view.
* Firewall: `ufw allow 80,443/tcp && ufw enable`.
* `DEBUG=false` → cookie'lar `Secure`, xatolar yashirin.
* Django admin uchun kuchli parol; xohlasangiz nginx darajasida IP
  allowlist.
* Payme/Click panelida callback URL'larni `https://app.doocall.uz/...`
  ga yangilang.

## Env knobs (Phase 9)

| Var | Default | Meaning |
|---|---|---|
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` | 4 / 2 | backend concurrency |
| `CELERY_CONCURRENCY` | 4 | worker processes |
| `AUDIO_PRESIGN_EXPIRY_SECONDS` | 3600 | presigned URL TTL (hard-capped at 1h) |
| `AUDIO_RETENTION_DAYS` | 30 | global audio retention |
| `PUBLIC_PRICING_CACHE_SECONDS` | 60 | landing pricing cache |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_RATE` | off | error tracking |
