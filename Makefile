# auto-tessell — common developer commands
# Run from the project root.

PYTHON ?= python3
PIP    ?= pip3

# ── Backend ──────────────────────────────────────────────────────────────────

.PHONY: install
install:  ## Install Python dependencies
	cd backend && $(PIP) install -r requirements.txt

.PHONY: dev
dev:  ## Start FastAPI dev server (SQLite, no Docker needed)
	cd backend && uvicorn main:app --reload --port 8000

.PHONY: worker-dev
worker-dev:  ## Start Celery worker in dev mode (requires Redis)
	cd backend && celery -A worker.celery_app worker --loglevel=info --concurrency=1

.PHONY: test
test:  ## Run unit tests (438 tests, fast)
	cd backend && $(PYTHON) -m pytest tests/ -v

.PHONY: test-integration
test-integration:  ## Run integration tests (89 tests, real FastAPI+SQLite)
	cd backend && $(PYTHON) -m pytest integration/ -v

.PHONY: test-all
test-all:  ## Run unit tests then integration tests
	cd backend && $(PYTHON) -m pytest tests/ -q && $(PYTHON) -m pytest integration/ -q

.PHONY: typecheck
typecheck:  ## TypeScript type check (no emit)
	cd frontend && npx tsc --noEmit

# ── Frontend ─────────────────────────────────────────────────────────────────

.PHONY: frontend
frontend:  ## Start Next.js dev server
	cd frontend && npm run dev

.PHONY: frontend-install
frontend-install:  ## Install Node dependencies
	cd frontend && npm install

.PHONY: frontend-build
frontend-build:  ## Build Next.js for production
	cd frontend && npm run build

# ── Docker Compose ───────────────────────────────────────────────────────────

.PHONY: up
up:  ## Start full stack (db + redis + api + worker)
	docker compose up --build

.PHONY: up-d
up-d:  ## Start full stack in background
	docker compose up --build -d

.PHONY: down
down:  ## Stop and remove containers
	docker compose down

.PHONY: logs
logs:  ## Follow all container logs
	docker compose logs -f

.PHONY: logs-api
logs-api:  ## Follow API container logs
	docker compose logs -f api

.PHONY: logs-worker
logs-worker:  ## Follow worker container logs
	docker compose logs -f worker

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
