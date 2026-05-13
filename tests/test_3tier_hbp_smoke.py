"""3-tier (tet/hex/poly) × test_cube smoke regression.

Locks in the H-series (hex+cfMesh), P-series (poly+cfMesh cartesian_dual),
and U-series (tet+BL) achievements: each mesh_type produces a PASS or
PASS_WITH_WARNINGS verdict on the canonical test_cube STL at draft
quality with target_cells=10000 / BL=3.

Heavy: each subtest spawns cfMesh / cfMesh+polyDualMesh / fTetWild
under ~30-90 s.  Skipped when OpenFOAM env not present.

Run::

    pytest tests/test_3tier_hbp_smoke.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CUBE_STL = REPO_ROOT / "test_cube.stl"


def _have_openfoam() -> bool:
    """Return True if cartesianMesh is on PATH or OPENFOAM_DIR is set."""
    if shutil.which("cartesianMesh"):
        return True
    for of_root in ("/usr/lib/openfoam/openfoam2406",
                    "/opt/openfoam2406",
                    os.environ.get("OPENFOAM_DIR", "")):
        if of_root and Path(of_root).exists():
            return True
    return False


pytestmark = pytest.mark.skipif(
    not _have_openfoam() or not CUBE_STL.exists(),
    reason="needs OpenFOAM 2406 + test_cube.stl",
)


def _h_series_env() -> dict[str, str]:
    """Hex+cfMesh series default env (mirrors GUI _DEFAULT_ENV)."""
    return {
        "AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM": "1",
        "AUTO_TESSELL_HEX_CFMESH_TARGET_CALIB": "0.85",
        "AUTO_TESSELL_HEX_CFMESH_REPAIR_SURFACE": "1",
        "AUTO_TESSELL_BL_DROP_NEG_VOL": "1",
        "AUTO_TESSELL_BL_DROP_NEG_VOL_GEOM_CHECK": "0",
        "AUTO_TESSELL_BL_DROP_NEG_VOL_TOPO_CHECK": "1",
        "AUTO_TESSELL_BL_DROP_SKEW_THRESHOLD": "18",
        "AUTO_TESSELL_BL_DROP_MAX_ITER": "24",
        "AUTO_TESSELL_POLY_BACKEND": "cartesian_dual",
        "AUTO_TESSELL_POLY_CFMESH_REPAIR_SURFACE": "1",
        "AUTO_TESSELL_POLY_CFMESH_TARGET_CALIB": "1.4",
        "PYTHONUNBUFFERED": "1",
    }


def _run_cli(
    mesh_type: str, out_dir: Path, *, extra_tier_params: list[str] | None = None,
    timeout: float = 600.0,
) -> dict:
    """Run the auto-tessell CLI on test_cube and return parsed quality_report."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [
        sys.executable, "-m", "cli.main", "run", str(CUBE_STL),
        "-o", str(out_dir),
        "--mesh-type", mesh_type,
        "--quality", "draft",
        "--checker-engine", "native",
        "--auto-retry", "off",
        "--max-cells", "10000",
        "--bl-layers", "3",
        "--tier-param", "target_cells=10000",
        "--tier-param", "max_cells=10000",
        "--tier-param", "cfmesh_bl_n_layers=3",
        "--tier-param", "bl_layers=3",
        "--tier-param", "post_layers_engine=disabled",
    ]
    if extra_tier_params:
        for tp in extra_tier_params:
            cmd.extend(["--tier-param", tp])
    env = os.environ.copy()
    env.update(_h_series_env())
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    qp = out_dir / "quality_report.json"
    assert qp.exists(), (
        f"quality_report.json missing for mesh_type={mesh_type!r}; "
        f"rc={proc.returncode}; tail={proc.stdout[-500:]}"
    )
    return json.loads(qp.read_text())


def _assert_pass_states(report: dict, mesh_type: str) -> None:
    """Verdict must be PASS or PASS_WITH_WARNINGS (no hard fail)."""
    s = report.get("evaluation_summary", {})
    verdict = s.get("verdict", "")
    cm = s.get("checkmesh", {})
    cells = cm.get("cells", 0)
    assert verdict in ("PASS", "PASS_WITH_WARNINGS"), (
        f"{mesh_type}: verdict={verdict!r} cells={cells} "
        f"hard_fails={s.get('hard_fails')} soft_fails={s.get('soft_fails')}"
    )
    assert cells > 100, f"{mesh_type}: too few cells ({cells})"
    assert cm.get("negative_volumes", 0) == 0, (
        f"{mesh_type}: negative_volumes={cm.get('negative_volumes')}"
    )


def test_hex_dominant_cube_smoke(tmp_path: Path) -> None:
    """H-series: hex_dominant + cfMesh cartesianMesh + BL3 on test_cube."""
    report = _run_cli("hex_dominant", tmp_path / "hex")
    _assert_pass_states(report, "hex_dominant")
    cells = report["evaluation_summary"]["checkmesh"]["cells"]
    # H-1 maxCellSize remap should pull test_cube above the cfMesh
    # default 1.7k cell count.  PSS=21/21 bench typically gives 22k.
    assert cells > 5000, f"H-1 remap may have regressed: cells={cells}"


def test_poly_cube_smoke(tmp_path: Path) -> None:
    """Poly backend: tet_dual default (fTetWild + polyDualMesh)."""
    report = _run_cli("poly", tmp_path / "poly")
    _assert_pass_states(report, "poly")
    cells = report["evaluation_summary"]["checkmesh"]["cells"]
    # QA-fix (2026-05-13): default backend is now ``tet_dual`` which
    # produces TRUE polyhedral cells (pentagon/hexagon dominant) at
    # roughly target/2 cells (target=10000 → ~5000 cells with
    # PRIMAL_SCALE=3.0 default).  Accept a wide window since fTetWild
    # cell count depends on input geometry.
    assert cells > 1000, (
        f"poly tet_dual: cells={cells} — polyDualMesh may not have run"
    )


def test_tet_cube_smoke(tmp_path: Path) -> None:
    """U-series: tet + wildmesh/native_tet + native_bl 3-layer."""
    # Tet path may use pytetwild fallback; allow either native or
    # external since U-series 21/21 is the wildmesh tier baseline.
    report = _run_cli(
        "tet", tmp_path / "tet",
        timeout=900.0,
    )
    _assert_pass_states(report, "tet")
    cells = report["evaluation_summary"]["checkmesh"]["cells"]
    assert cells > 100, f"tet: too few cells ({cells})"


def test_gui_default_env_keys_present() -> None:
    """desktop/qt_main.py _DEFAULT_ENV must include all H/P series knobs."""
    sys.path.insert(0, str(REPO_ROOT))
    from desktop.qt_main import _DEFAULT_ENV
    required = [
        # H-series (hex+cfMesh)
        "AUTO_TESSELL_HEX_CFMESH_TARGET_CALIB",
        "AUTO_TESSELL_HEX_CFMESH_REPAIR_SURFACE",
        "AUTO_TESSELL_BL_DROP_NEG_VOL_GEOM_CHECK",
        "AUTO_TESSELL_BL_DROP_NEG_VOL_TOPO_CHECK",
        "AUTO_TESSELL_BL_DROP_MAX_ITER",
        "AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM",
        # P-series (poly+cfMesh cartesian_dual)
        "AUTO_TESSELL_POLY_BACKEND",
        "AUTO_TESSELL_POLY_CFMESH_REPAIR_SURFACE",
        "AUTO_TESSELL_POLY_CFMESH_TARGET_CALIB",
    ]
    missing = [k for k in required if k not in _DEFAULT_ENV]
    assert not missing, (
        f"GUI _DEFAULT_ENV missing H/P series knobs: {missing}.  "
        f"Without these, GUI 3-tier mesh_type runs fall back to "
        f"baseline behaviour and lose the 21/21 PSS achievement."
    )


def test_canonical_tier_poly_aliases() -> None:
    """tier_selector must map ``cfmesh_poly`` to ``tier_cfmesh_poly``."""
    sys.path.insert(0, str(REPO_ROOT))
    from core.strategist.tier_selector import canonical_tier
    assert canonical_tier("cfmesh_poly") == "tier_cfmesh_poly"
    assert canonical_tier("polyhedral") == "tier_polyhedral"
    # cfmesh defaults to cartesianMesh (hex), poly translation happens
    # in main_window.py before tier_hint reaches the strategist.
    assert canonical_tier("cfmesh") == "tier15_cfmesh"
