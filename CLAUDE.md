# Auto-Tessell — CLAUDE.md

Automated CAD/mesh files → OpenFOAM polyMesh generator.

**Core philosophy — native-first.** External mesh libraries (TetWild, fTetWild/WildMesh,
snappyHexMesh, cfMesh, pymeshfix, pyACVD, geogram) are **reference-only**; their core
algorithms are ported into `core/` so the tool eventually runs with no external mesh
dependency. **B+C fallback policy:** self-implemented engines run first; only meshes that
fail to reach grade A fall back to an external lib (e.g. `pytetwild.tetrahedralize`).
Set env `AUTO_TESSELL_P4C_PYTETWILD=0` to disable the fallback (native-only measurement).

## Project Map

| Path | Role |
|------|------|
| `core/` | Engine (see sub-table below). |
| `core/analyzer/` | Native file readers (STL/OBJ/PLY/OFF/STEP…) + geometry & topology analysis. |
| `core/preprocessor/` | Surface prep: `native_repair/` (L1), `native_remesh/` (L2), `l3_ai_surface_repair` (L3). |
| `core/strategist/` | mesh_type × quality → tier selection (`tier_selector.py`). |
| `core/generator/` | Volume engines: `native_tet/ native_hex/ native_poly/` + reference tiers (`tier2_tetwild.py`, …), `pipeline.py`. |
| `core/layers/` | Boundary layers (`native_bl.py`). |
| `core/evaluator/` | `native_checker.py` (NativeMeshChecker) + quality report. |
| `core/pipeline/` | `orchestrator.py` — full pipeline driver. |
| `core/utils/` | polyMesh reader/writer, `geometry.py` (GWN inside-test), `surface_nets.py` (reconstruction), `drop_neg_vol_cells.py`, `mesh_exporter.py`. |
| `cli/` | CLI entry point (click + rich). |
| `desktop/` | GUIs — see desktop sub-table. |
| `agents/specs/` | Agent + CLI parameter specs (`*.md`). |
| `tests/` | pytest suite + benchmarks (`verify_goal.py`, `bench_quality_matrix.py`, `stl/bench_*_cavity_eval.py`, `test_desktop_server.py`, `test_web_server_mapping.py`). |
| `installer/` | Windows NSIS/Inno click installer (Miniconda + conda env). |
| `backend/`, `frontend/` | Phase-2 Web SaaS scaffold (FastAPI + Next.js, Stripe) — separate product direction. |
| `third_party/`, `AlgoHex/`, `HOHQMesh/`, `VoroCrust/`, `tessell-mesh/`, `Feature-Preserving-Octree-Hex-Meshing/` | Reference/vendored engine sources. |
| `godot/` | **Legacy** Godot GUI — superseded by Qt + Web/Electron. |

### `desktop/` GUIs

| Path | Role |
|------|------|
| `desktop/qt_app/` | PySide6 Qt GUI (launched via `desktop/qt_main.py`). |
| `desktop/server.py` | FastAPI + WebSocket backend serving the web GUI (port 9720). |
| `desktop/web/` | Dependency-free SPA + WebGL viewer. |
| `desktop/electron/` | Frameless Electron desktop app wrapping the web GUI. |
| `desktop/default_env.py` | Shared `AUTO_TESSELL_*` defaults. |

## Architecture

**5-agent pipeline:** `Analyzer → Preprocessor → Strategist → Generator → Evaluator`.
There is **no automatic Generator↔Evaluator retry loop** — on FAIL the Evaluator prints a
recommendation and asks the user `y/N`. The Generator keeps its own internal fallback
(same mesh_type, different tier). Detailed agent + CLI specs live in `agents/specs/*.md`.

**Two phases:**

1. **Surface mesh** — L1 repair → L2 remesh → L3 AI/voxel reconstruct.
   Gate to Phase 2 = watertight + manifold.
2. **Volume mesh** — user picks `mesh_type ∈ {tet, hex_dominant, poly}`, each × quality
   `{draft, standard, fine}` maps to a tier (table below). A **Tier-4 boundary-layer** pass
   (per mesh_type) runs afterward.

### mesh_type × quality → tier

| mesh_type | draft | standard | fine |
|-----------|-------|----------|------|
| tet | tetwild (coarse ε) | netgen / wildmesh | wildmesh (tight ε) |
| hex_dominant | cfmesh (fast) | cfmesh | snappyHexMesh (+BL) |
| poly | voro_poly | polydual | polydual + quality pass |

## Running

```bash
# CLI
auto-tessell run input.stl -o ./case --mesh-type tet --quality draft
auto-tessell run input.stl -o ./case --tier native_hex --auto-retry off   # force a native engine

# Qt GUI
python desktop/qt_main.py

# Web GUI  → http://localhost:9720/
./start_web_gui.sh          # or start_web_gui.bat on Windows

# Electron app
cd desktop/electron && npm install && npm start

# Verify / bench
python tests/verify_goal.py           # 3 mesh_types on a cube
python tests/bench_quality_matrix.py  # 12 STL × 3 types quality matrix
```

## Conventions & References

- **Detailed rules → `.claude/rules/`:** `coding-style.md`, `lessons-learned.md`,
  `communication.md` (read these before non-trivial work).
- **Version history → `CHANGELOG.md`** (do not re-add version walls here).
- **Agent / CLI specs → `agents/specs/`.**
- **Robust-meshing design → `ROBUSTNESS_REPORT.md`.**
- **Dev env:** Python 3.12+, C++23, OpenFOAM 2406, Node.js 24.

## Execution Model

See [.claude/rules/execution-model.md](.claude/rules/execution-model.md) — Advisor / Worker roles, delegation, verification, and report timing.

## Skill routing

When a request matches an available skill, invoke it via the Skill tool as the FIRST action
(don't answer directly first). Common routes: bugs/errors → `investigate`; ship/deploy/PR →
`ship`; QA/test the site → `qa`; code review → `review`; docs after shipping →
`document-release`; architecture review → `plan-eng-review`.
