# auto-tessell

STL → OpenFOAM polyMesh SaaS. Upload a `.stl` file, get a CFD or FEA-ready
mesh back as a ZIP.

---

## Quick start (dev mode — no Docker, no Stripe, no S3)

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
cp ../.env.example .env       # DEV_MODE=true already set
uvicorn main:app --reload     # http://localhost:8000

# 2. Frontend
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                   # http://localhost:3000
```

Or use `make dev` (backend) + `make frontend` (frontend) from the project root.

---

## Architecture

```
frontend (Next.js 14)
    │  REST  /api/v1/*
    ▼
backend/main.py (FastAPI)
    ├── POST /upload          STL validation → job create → queue mesh task
    ├── POST /webhook         Stripe payment_intent.succeeded → start task
    ├── GET  /jobs            List recent jobs for a user
    ├── GET  /jobs/{id}       Poll job status
    ├── DELETE /jobs/{id}     Remove a terminal job
    └── GET  /jobs/{id}/download  Presigned S3 URL (or local in dev mode)

worker/tasks.py (Celery + Redis)
    └── run_mesh(job_id)
        ├── Download STL (local in dev, S3 in prod)
        ├── generate_mesh() → 5-tier pipeline
        ├── Upload polyMesh ZIP (local in dev, S3 in prod)
        └── On failure: Stripe refund + FAILED/REFUND_FAILED status

mesh/generator.py
    └── 5-tier pipeline (Tier 0 → Tier 2, first success wins)
```

### 5-tier mesh pipeline

| Tier | Engine | License | Notes |
|------|--------|---------|-------|
| 0 | tessell_mesh / geogram | BSD-3-Clause | C++/pybind11, fastest; `./build.sh` in `tessell-mesh/` |
| 0.5 | Netgen | LGPL-2.1 | `pip install netgen-mesher` |
| 1 | snappyHexMesh | GPL (OpenFOAM) | CFD only; requires OpenFOAM 12 Docker |
| 2 | pytetwild + MMG | MPL-2.0 + LGPL-3.0 | Final fallback; MMG optional quality pass |

Dev mode uses pytetwild directly (no Docker needed).

---

## Pro mode parameters

Users can override per-tier mesh quality knobs in the UI:

| Parameter | Tier | Range | Effect |
|-----------|------|-------|--------|
| `tet_stop_energy` | pytetwild | 0.5–100 | Quality vs speed (lower = better) |
| `tet_edge_length_fac` | pytetwild | 0.02–0.20 | Cell size relative to bbox diagonal |
| `snappy_refine_min/max` | snappyHexMesh | 0–6 | Surface refinement levels |
| `snappy_n_layers` | snappyHexMesh | 0–12 | Boundary layer cells |
| `snappy_expansion_ratio` | snappyHexMesh | 1.05–2.0 | Layer growth ratio |
| `snappy_max_non_ortho` | snappyHexMesh | 50–85° | Quality gate |
| `netgen_maxh_ratio` | Netgen | 2–100 | maxh = L / ratio |
| `mmg_enabled` | MMG | bool | Enable/disable post-processing |
| `mmg_hausd` | MMG | 1e-6–1.0 | Surface fidelity |
| `mmg_hgrad` | MMG | 1.0–5.0 | Size gradation |

---

## Testing

```bash
# Unit tests (no external services needed)
make test               # 128 tests

# Integration tests (real FastAPI + in-memory SQLite)
make test-integration   # 48 tests

# Both
make test-all
```

---

## Full stack (Docker Compose)

```bash
cp .env.example .env    # fill in STRIPE_*, AWS_*, DEV_MODE=false
make up                 # starts db + redis + api + worker
```

---

## Job state machine

```
PENDING → PAID → PROCESSING → DONE
                             ↘ FAILED → (Stripe refund attempt)
                                       → REFUND_FAILED
```

---

## License summary (SaaS-safe)

All mesh libraries used are MIT/BSD/MPL/LGPL — safe for SaaS without
source disclosure. OpenFOAM runs server-side only (not distributed).
See `CLAUDE.md` for full table.
