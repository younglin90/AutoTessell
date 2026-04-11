# AutoTessell Track Ownership

Date: 2026-04-08

## Purpose

Define clear ownership for each product track to reduce decision latency and doc/code drift.

## Tracks

| Track | Scope | Primary Owner | Backup Owner | Current Status |
|------|------|---------------|--------------|----------------|
| `core+cli` | `core/`, `cli/`, root pipeline docs | repo-maintainer | desktop-maintainer | Active |
| `desktop` | `godot/`, `desktop/`, desktop tests | desktop-maintainer | repo-maintainer | Active (Godot primary, Qt prototype) |
| `web` | `backend/`, `frontend/`, web integration tests | web-maintainer | repo-maintainer | Active (demo/validation) |

## Assignment Policy

- Acceptable temporary owner values (role-based): `repo-maintainer`, `desktop-maintainer`, `web-maintainer`.
- Owner assignment changes must be logged in `OWNERSHIP_DECISIONS.md`.

## Decision SLA

- Cross-track breaking decision: owner sync required within 2 business days.
- Doc baseline updates (`README`, `PLAN`, `SPEC`): same PR as code change.
- Version changes: all public entrypoints must be updated together.

## Review Cadence

- Weekly: check doc consistency and roadmap status.
- Before release tag: verify version and track status tables.
