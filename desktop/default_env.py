"""Shared default environment knobs for Auto-Tessell GUIs.

Both the Qt desktop GUI (``desktop/qt_main.py``) and the web GUI server
(``desktop/server.py``) apply this identical set of ``AUTO_TESSELL_*`` env
defaults so that a mesh produced from the browser matches, bit-for-bit, what
the Windows desktop GUI produces.

This module intentionally has **no Qt / PySide6 import** so the headless web
server can apply the same defaults without pulling in a GUI toolkit.

Keep this in sync with the v1.1 "3-Tier × 21-STL 21/21 PSS" bench defaults
(see ``CLAUDE.md`` and ``tests/stl/bench_*_cavity_eval.py``).  Dropping these
knobs degrades the 21-STL results (tet/hex/poly) below 21/21.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# GUI-DEFAULT / beta2810 — optimal defaults activated the moment a GUI starts.
# Self-impl tet hardening + multi-fallback chain + BL aspect cap +
# P4-C pytetwild fallback + poly tet_dual backend, etc.
# ---------------------------------------------------------------------------
DEFAULT_ENV: dict[str, str] = {
    # --- self-impl tet hardening ---------------------------------------
    "AUTO_TESSELL_STELLAR_KLINGNER": "1",       # Klingner edge contract (P2.1).
    "AUTO_TESSELL_BL_ASPECT_ENFORCE": "1",      # post-extrude aspect cap.
    "AUTO_TESSELL_BL_ASPECT_TARGET": "1000",
    "AUTO_TESSELL_P4C_PYTETWILD": "1",          # P4-C external fallback.
    "AUTO_TESSELL_VVV2_QUEUE": "1",             # Stellar swap queue.
    "AUTO_TESSELL_RRR2_TARGETED": "1",          # AMIPS targeted smoothing.
    "AUTO_TESSELL_P3_SSS_REVIVAL": "1",         # surface vertex relocate.
    "AUTO_TESSELL_CVT3D_QUALITY_WEIGHT": "0",   # opt-in only (heavier).
    "AUTO_TESSELL_AGGR_REPAIR": "0",            # off by default (heavier).
    "AUTO_TESSELL_L3_AI_REPAIR": "0",           # off by default (very heavy).
    "AUTO_TESSELL_POLY_GRADE_RETRY": "1",       # poly retry chain.
    # --- U-series (tet+BL) — parity with bench_cavity_eval.py ----------
    "AUTO_TESSELL_BL_TRIANGULATE_QUAD_SHORTEST": "1",        # U-1
    "AUTO_TESSELL_BL_DROP_NEG_VOL": "1",                     # U-3
    "AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD": "10",             # U-3b + QA
    "AUTO_TESSELL_WILDMESH_TARGET_CELL_REMAP": "1",          # U-13
    "AUTO_TESSELL_WILDMESH_TARGET_CALIB_BASE": "14000",
    "AUTO_TESSELL_WILDMESH_TARGET_OVERSHOOT": "1.4",
    "AUTO_TESSELL_WILDMESH_BOX_TARGET_FRAC": "0.95",         # U-12
    "AUTO_TESSELL_WILDMESH_EXTRUSION_TARGET_FACTOR": "1.5",  # U-17
    "AUTO_TESSELL_WILDMESH_EXTRUSION_OUTER_FACTOR": "0.9",
    # --- H-series (hex+cfMesh+BL) — parity with bench_hex_cavity_eval.py
    "AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM": "1",             # cfMesh external
    "AUTO_TESSELL_HEX_CFMESH_TARGET_CALIB": "0.85",          # H-2
    "AUTO_TESSELL_HEX_CFMESH_REPAIR_SURFACE": "1",           # H-10 WildMesh repair
    "AUTO_TESSELL_BL_DROP_NEG_VOL_GEOM_CHECK": "0",          # H-6 hex-safe
    "AUTO_TESSELL_BL_DROP_NEG_VOL_TOPO_CHECK": "1",
    # hex+BL broken-input cleanup needs more iters than tet loop's 8 → 24.
    "AUTO_TESSELL_BL_DROP_MAX_ITER": "24",                   # H-7 (supersedes 8)
    # --- P-series (poly+cfMesh) — parity with bench_poly_cavity_eval.py
    # ``tet_dual`` = fTetWild + polyDualMesh → true polyhedral cells.
    "AUTO_TESSELL_POLY_BACKEND": "tet_dual",                 # P-3 QA upgrade
    "AUTO_TESSELL_POLY_TETDUAL_PRIMAL_SCALE": "3.0",         # primal cell scale
    "AUTO_TESSELL_POLY_CFMESH_REPAIR_SURFACE": "1",          # P-1 WildMesh repair
    "AUTO_TESSELL_POLY_CFMESH_TARGET_CALIB": "1.4",          # P-2 pMesh density
}


def apply_default_env() -> None:
    """Apply default env knobs that the user has not already set.

    Uses ``setdefault`` so any value already present in ``os.environ`` (e.g.
    a user override or a bench script's forced setting) takes precedence.
    """
    for key, value in DEFAULT_ENV.items():
        os.environ.setdefault(key, value)
