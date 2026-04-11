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
test:  ## Run unit tests
	cd backend && $(PYTHON) -m pytest tests/ -v

.PHONY: test-integration
test-integration:  ## Run integration tests (FastAPI+SQLite)
	cd backend && $(PYTHON) -m pytest integration/ -v

.PHONY: test-all
test-all:  ## Run unit tests then integration tests
	cd backend && $(PYTHON) -m pytest tests/ -q && $(PYTHON) -m pytest integration/ -q

.PHONY: typecheck
typecheck:  ## TypeScript type check (no emit)
	cd frontend && npx tsc --noEmit

.PHONY: test-count
test-count:  ## Show current test file counts (dynamic)
	@echo "root tests:" $$(find tests -name 'test_*.py' | wc -l)
	@echo "backend unit tests:" $$(find backend/tests -name 'test_*.py' | wc -l)
	@echo "backend integration tests:" $$(find backend/integration -name 'test_*.py' | wc -l)

.PHONY: baseline-check
baseline-check:  ## Check baseline drift (version/test-count stale strings)
	@! rg -n "0\.1\.0|331\+|458\+|621 tests|89 tests" README.md PLAN.md SPEC.md backend/main.py desktop/server.py

.PHONY: version-check
version-check:  ## Check app-version consistency across key files
	@$(PYTHON) scripts/check_version.py

.PHONY: docs-check
docs-check:  ## Check docs baseline links and stale wording
	@rg -n "CURRENT_STATUS_AND_BACKLOG.md|TRACK_OWNERSHIP.md|RELEASE_CHECKLIST.md|TEST_COUNTING_POLICY.md" README.md >/dev/null
	@! rg -n "테스트 [0-9]+\+|tests? [0-9]+\+" README.md PLAN.md SPEC.md

.PHONY: owner-check-soft
owner-check-soft:  ## Fail if ownership docs still contain TODO
	@! rg -n "TODO" TRACK_OWNERSHIP.md OWNERSHIP_DECISIONS.md

.PHONY: owner-check
owner-check:  ## Strict owner check: no TODO and no UNASSIGNED
	@! rg -n "TODO|UNASSIGNED" TRACK_OWNERSHIP.md OWNERSHIP_DECISIONS.md

.PHONY: checks-soft
checks-soft: version-check baseline-check docs-check owner-check-soft test-count  ## Run soft governance checks

.PHONY: checks-strict
checks-strict: version-check baseline-check docs-check owner-check test-count  ## Run strict governance checks

.PHONY: smoke-check
smoke-check:  ## Run minimal cross-track health tests
	@$(PYTHON) -m pytest -q tests/test_desktop_server.py -k health
	@$(PYTHON) -m pytest -q backend/tests/test_main_endpoints.py

.PHONY: gui-offscreen-smoke
gui-offscreen-smoke:  ## Smoke-run Qt GUI in offscreen mode (no display needed)
	@QT_QPA_PLATFORM=offscreen $(PYTHON) -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from desktop.qt_app.main_window import AutoTessellWindow; app=QApplication([]); win=AutoTessellWindow(); win.show(); QTimer.singleShot(300, app.quit); app.exec(); print('qt_offscreen_smoke_ok')"

.PHONY: gui-headless
gui-headless:  ## Run Qt GUI with Xvfb + x11vnc (view via VNC localhost:5900)
	@DISPLAY_NUM=$${DISPLAY_NUM:-99} VNC_PORT=$${VNC_PORT:-5900} APP_CMD="$${APP_CMD:-$(PYTHON) -m desktop.qt_main}" \
		bash scripts/run_qt_headless_vnc.sh

.PHONY: safeguard-regression
safeguard-regression:  ## Run required safeguard-focused regressions (quick local gate)
	@$(PYTHON) -m pytest -q \
		tests/test_openfoam_utils_extra.py \
		tests/test_case_writer.py::test_foamlib_fallback \
		tests/test_preprocessor.py::test_laplacian_smoothing_graceful_fallback_no_igl \
		tests/test_preprocessor.py::test_pygem_rbf_morph_safe_returns_original_on_failure \
		tests/test_strategist.py::TestStrategyPlannerAdditional::test_plan_snappy_params_int32_clamp \
		tests/test_strategist.py::TestTierSelector::test_quality_level_string_accepted \
		tests/test_cli.py::TestCLIHelp::test_doctor_command \
		tests/test_cli.py::TestRunDryRun::test_dry_run_max_cells_clamps_for_int32 \
		tests/test_orchestrator.py::TestRetryLoop::test_max_cells_applied_again_after_restrategize

.PHONY: qa-matrix-mini
qa-matrix-mini:  ## Quick matrix scan (quality x tier) on test_cube.stl
	@$(PYTHON) scripts/run_mesh_matrix.py \
		--repo-root . \
		--python-bin .venv/bin/python \
		--input ./test_cube.stl \
		--remesh-engine auto \
		--timeout-sec 10 \
		--timeout-by-tier netgen=30 \
		--timeout-by-tier snappy=30 \
		--timeout-by-tier cfmesh=30 \
		--timeout-by-tier tetwild=30 \
		--out-prefix mini_matrix

.PHONY: qa-matrix-mini-fast
qa-matrix-mini-fast:  ## Quick matrix with fast runtime profile (fewer timeouts)
	@$(PYTHON) scripts/run_mesh_matrix.py \
		--repo-root . \
		--python-bin .venv/bin/python \
		--input ./test_cube.stl \
		--remesh-engine auto \
		--runtime-profile fast \
		--timeout-sec 10 \
		--timeout-by-tier netgen=30 \
		--timeout-by-tier snappy=30 \
		--timeout-by-tier cfmesh=30 \
		--timeout-by-tier tetwild=30 \
		--out-prefix mini_matrix_fast

.PHONY: qa-matrix-full-cube
qa-matrix-full-cube:  ## Full matrix (quality x tier x remesh) on test_cube.stl
	@$(PYTHON) scripts/run_mesh_matrix.py \
		--repo-root . \
		--python-bin .venv/bin/python \
		--input ./test_cube.stl \
		--timeout-sec 20 \
		--timeout-by-quality standard=60 \
		--timeout-by-quality fine=90 \
		--timeout-by-tier netgen=120 \
		--timeout-by-tier snappy=120 \
		--timeout-by-tier cfmesh=120 \
		--timeout-by-tier tetwild=120 \
		--out-prefix full_matrix

.PHONY: qa-matrix-fine-fast
qa-matrix-fine-fast:  ## Fine-only tier matrix with fast profile (timeout/fail diagnostics)
	@$(PYTHON) scripts/run_mesh_matrix.py \
		--repo-root . \
		--python-bin .venv/bin/python \
		--input ./test_cube.stl \
		--quality fine \
		--tier auto \
		--tier core \
		--tier netgen \
		--tier snappy \
		--tier cfmesh \
		--tier tetwild \
		--remesh-engine auto \
		--runtime-profile fast \
		--timeout-sec 12 \
		--max-iter-by-tier auto=2 \
		--max-iter-by-tier netgen=2 \
		--max-iter-by-tier tetwild=3 \
		--out-prefix fast_fine_tiers_auto_remesh

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
