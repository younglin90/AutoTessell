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
	cd backend && DEV_MODE=true uvicorn main:app --reload --port 8000

.PHONY: test
test:  ## Run unit tests
	cd backend && $(PYTHON) -m pytest tests/ -v

.PHONY: test-integration
test-integration:  ## Run integration tests (unit tests + full endpoint tests)
	cd backend && $(PYTHON) -m pytest integration/ -v

.PHONY: test-all
test-all:  ## Run unit tests then integration tests
	cd backend && $(PYTHON) -m pytest tests/ -q && $(PYTHON) -m pytest integration/ -q

# ── Frontend ─────────────────────────────────────────────────────────────────

.PHONY: frontend
frontend:  ## Start Next.js dev server
	cd frontend && npm run dev

.PHONY: frontend-install
frontend-install:  ## Install Node dependencies
	cd frontend && npm install

# ── Docker Compose ───────────────────────────────────────────────────────────

.PHONY: up
up:  ## Start full stack (db + redis + api + worker)
	docker compose up --build

.PHONY: down
down:  ## Stop and remove containers
	docker compose down

.PHONY: logs
logs:  ## Follow all container logs
	docker compose logs -f

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
