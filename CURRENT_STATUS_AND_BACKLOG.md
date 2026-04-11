# AutoTessell Current Status and Priority Backlog

Date: 2026-04-08

## 1) Executive Summary

The repository has a strong `core` meshing engine, but product direction is split across three shells:

- Local CLI/Core pipeline (`cli/`, `core/`)
- Desktop app track (`godot/` + `desktop/server.py`, plus `desktop/qt_*` prototype)
- Web SaaS track (`backend/`, `frontend/`)

Main risk is not missing features. Main risk is baseline governance ambiguity (ownership and desktop-direction convergence remain open).

Progress update (2026-04-08):

- Baseline wording alignment applied in `README.md`, `PLAN.md`, `SPEC.md`, `Makefile`.
- App/API visible version aligned to `1.0.0` in backend and desktop server.
- Drift-prevention docs added: `RELEASE_CHECKLIST.md`, `TEST_COUNTING_POLICY.md`.
- Automated checks added: `make version-check`, `make baseline-check`, `make docs-check`, `make test-count`.
- Minimal cross-track health gate added: `make smoke-check`.
- CI test/release workflows now run baseline/doc checks before tests.
- Ownership gate is strict-enabled: CI runs `make checks-strict` (includes `make owner-check`).
- Windows release workflow is now gated by reusable `common-checks` preflight before packaging.

## 2) What Is Working Today

### 2.1 Core/CLI (most complete path)

- End-to-end pipeline exists:
  `Analyze -> Preprocess -> Strategize -> Generate <-> Evaluate`
  (`core/pipeline/orchestrator.py`)
- CLI commands for stage-by-stage and full run exist (`cli/main.py`).
- Evaluator falls back to native checker when OpenFOAM `checkMesh` is unavailable (`core/evaluator/quality_checker.py`).

Conclusion: `core + cli` is the most production-ready technical foundation in this repo.

### 2.2 Desktop

- Practical path today is Godot + desktop FastAPI/WebSocket server:
  `godot/project.godot` + `desktop/server.py`
- Qt path exists but is currently scaffold/prototype level:
  `desktop/qt_main.py`, `desktop/qt_app/*`

Conclusion: desktop implementation is currently dual-track and not converged.

### 2.3 Web SaaS

- Flow is functionally connected:
  upload -> payment intent/webhook -> celery job -> status poll -> download
  (`backend/api/upload.py`, `backend/api/payment.py`, `backend/worker/tasks.py`, `backend/api/download.py`, `frontend/app/mesh/*`)
- Good for internal demo/validation.
- Not ready for hardened production security/operations yet.

## 3) Baseline Status and Remaining Gaps

### 3.1 Version mismatch

Status update (2026-04-08):

- This mismatch is now aligned to `1.0.0` in:
  `pyproject.toml`, `backend/main.py`, `desktop/server.py`, `SPEC.md`.
- Keep this section as a checklist item to prevent regression.

### 3.2 GUI status mismatch

- Desktop current path is Godot.
- Qt migration remains a planned/partial path.
- Repo still contains both active Godot and Qt code paths.

### 3.3 Test scale mismatch

Status update (2026-04-08):

- Fixed hardcoded totals were removed from `README.md`, `PLAN.md`, `SPEC.md`, `Makefile`.
- Policy is now documented in `TEST_COUNTING_POLICY.md`.
- Use `make test-count` for point-in-time counts.

### 3.4 Product scope mismatch

Status update (2026-04-08):

- Primary track is explicitly declared as `core + cli` in `README.md` and `SPEC.md`.
- Desktop and Web SaaS remain active secondary tracks.

## 4) Priority Decisions (must decide before feature work)

1. Primary product track for next cycle:
   `core+cli` vs `desktop` vs `web`
2. Desktop direction:
   keep Godot, or commit to Qt migration
3. Single versioning policy:
   one semantic version across root package/docs/backend API
4. Single documentation baseline:
   source-of-truth docs and ownership

## 5) Priority Backlog

## P0 (Do immediately)

- Create a single baseline doc and align all headline facts:
  version, primary product, desktop direction, test counting rule.
- Update `README.md`, `PLAN.md`, `SPEC.md`, `Makefile` comments to same baseline.
- Declare owner per product track (core, desktop, web).

Current status:

- Baseline doc created: done (`CURRENT_STATUS_AND_BACKLOG.md`)
- Doc wording alignment: done (initial pass)
- Owner declaration by track: role-based owners assigned (`TRACK_OWNERSHIP.md`)

Definition of done:

- No contradiction across root docs for version/scope/test scale/GUI direction.

## P1 (After baseline alignment)

- Run one end-to-end golden path and lock it:
  recommended: `core+cli` pipeline on representative STL/STEP samples.
- Add CI-visible status for the chosen golden path.
- For desktop: if Godot remains primary, mark Qt as experimental in docs.
  If Qt becomes primary, define feature parity checklist vs Godot.

Definition of done:

- One canonical path is executable and documented from setup to output artifacts.

## P2 (Product hardening)

- Web SaaS security hardening:
  replace ad-hoc `user_id` identity model with real auth boundary.
- Worker/job operability:
  progress model, retry strategy, cancellation/timeouts, idempotency.
- Observability and runbook:
  failure modes, queue/worker health, webhook reliability.

Definition of done:

- Web path can be operated with clear auth, failure handling, and support workflow.

## 6) Suggested 2-Week Execution Order

Week 1:

1. Baseline decision meeting (product focus + desktop direction + version policy)
2. Docs alignment PR (README/PLAN/SPEC/Makefile)
3. Golden path E2E validation and CI gate

Week 2:

1. Desktop convergence action (Godot-primary cleanup OR Qt migration start)
2. Web auth boundary design and first implementation slice
3. Worker/job reliability improvements (retry + progress + timeout taxonomy)

## 7) Immediate Next Action

Open a single alignment PR first (docs/version/scope/test-count consistency).
Do not start new feature work before this PR lands.
