# dooCall — developer entrypoints. Everything runs in containers so the host
# only needs Docker + make.
COMPOSE ?= docker compose
BACKEND_RUN = $(COMPOSE) run --rm backend
FRONTEND_RUN = $(COMPOSE) run --rm frontend

.DEFAULT_GOAL := help
.PHONY: help up down build test test-backend test-frontend lint lint-backend \
        lint-frontend typecheck migrate seed logs ps shell env

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

up: env ## Build + start the full stack (detached)
	$(COMPOSE) up -d --build

down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

build: env ## Build all images
	$(COMPOSE) build

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Tail logs for all services (make logs s=backend for one)
	$(COMPOSE) logs -f $(s)

# ── Tests ──────────────────────────────────────────────────────────────────
test: test-backend test-frontend ## Run all tests

test-backend: env ## Run backend pytest suite with coverage
	$(BACKEND_RUN) pytest --cov --cov-report=term-missing

test-frontend: ## Run frontend Vitest suite
	$(FRONTEND_RUN) npm run test

# ── Lint / typecheck ───────────────────────────────────────────────────────
lint: lint-backend lint-frontend ## Lint + typecheck everything

lint-backend: env ## ruff + mypy
	$(BACKEND_RUN) sh -c "ruff check . && ruff format --check . && mypy ."

lint-frontend: ## eslint + prettier + tsc
	$(FRONTEND_RUN) sh -c "npm run lint && npm run format && npm run typecheck"

typecheck: ## Type-check backend + frontend
	$(BACKEND_RUN) mypy .
	$(FRONTEND_RUN) npm run typecheck

# ── Django lifecycle ───────────────────────────────────────────────────────
migrate: env ## Apply database migrations
	$(BACKEND_RUN) python manage.py migrate

seed: env ## Seed demo tenant (Ahlan House, 6 operators, ~12k calls)
	$(BACKEND_RUN) python manage.py seed_demo

shell: ## Open a Django shell
	$(BACKEND_RUN) python manage.py shell
