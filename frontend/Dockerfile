# syntax=docker/dockerfile:1
# Dev image: installs deps and runs `next dev`. Prod multi-stage build lands
# in Phase 9 (docker-compose.prod.yml).
FROM node:22-slim

ENV NODE_ENV=development
WORKDIR /app

# curl for the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install deps first for layer caching. Falls back to `npm install` when no
# lockfile is present yet (Phase 1 ships without a committed lockfile).
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
