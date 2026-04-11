# AutoTessell Release Checklist

Date: 2026-04-08

## Scope

Use this checklist before creating a release tag.

## 1) Baseline Consistency

- [ ] `make version-check` passes.
- [ ] `pyproject.toml` version matches public entrypoints.
- [ ] `backend/main.py` FastAPI version matches project version.
- [ ] `desktop/server.py` app/health version matches project version.
- [ ] `desktop/qt_main.py` Qt app version matches project version.
- [ ] `godot/project.godot` `config/version` matches project version.
- [ ] `scripts/installer.iss` installer version matches project version.
- [ ] `frontend/package.json` version policy is applied (aligned or intentionally independent).
- [ ] `README.md`, `PLAN.md`, `SPEC.md` have no conflicting product-scope statements.
- [ ] `README.md`, `PLAN.md`, `SPEC.md`, `Makefile` have no stale hardcoded test totals.

## 2) Track Ownership

- [ ] `TRACK_OWNERSHIP.md` owners are filled (no `UNASSIGNED` left) for strict releases.
- [ ] `make owner-check` passes for strict releases.
- [ ] `make checks-strict` passes for strict releases.
- [ ] Reusable workflow `.github/workflows/common-checks.yml` remains the single source of strict baseline checks.
- [ ] Cross-track changes in this release were reviewed by affected track owners.

## 3) Test and Validation

- [ ] Core CLI golden path executed on representative sample(s).
- [ ] Desktop health and minimal flow tests pass.
- [ ] Backend health/config endpoint tests pass.
- [ ] `make smoke-check` passes.
- [ ] No new failing tests in touched modules.

## 4) Documentation

- [ ] Changelog/release notes updated.
- [ ] Any behavior change reflected in `README.md`.
- [ ] If roadmap status changed, `PLAN.md` updated in same release.

## 5) Go/No-Go

- [ ] Final `git diff` reviewed for accidental scope creep.
- [ ] Release decision recorded with date and owner.
