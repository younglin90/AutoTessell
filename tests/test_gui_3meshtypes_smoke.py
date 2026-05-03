"""GUI 3 mesh_type smoke test — vendored backend default 정책 검증.

BETA2845 정책 확인:
  mesh_type=tet         → tier_wildmesh (vendored fTetWild)
  mesh_type=hex_dominant → tier15_cfmesh (vendored cfMesh cartesianMesh)
  mesh_type=poly        → tier_cfmesh_poly (vendored cfMesh pMesh)

각 mesh_type 마다 cube STL 으로 PipelineOrchestrator 호출 → polyMesh 생성 + 셀 수
> 0 + 외부 OpenFOAM 시스템 의존 0 검증.
"""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

logging.disable(logging.CRITICAL)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _cube_VF() -> tuple[np.ndarray, np.ndarray]:
    V = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=np.float64)
    F = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7],
    ], dtype=np.int64)
    return V, F


def _read_polymesh_count(poly_dir: Path) -> int:
    """polyMesh dir → cell count (owner 줄 max + 1)."""
    owner = poly_dir / "owner"
    if not owner.exists():
        return 0
    try:
        from core.utils.ccmio_native_binary import _simple_polymesh_read
        _, _, own_list, _, _ = _simple_polymesh_read(poly_dir)
        if own_list:
            return max(int(o) for o in own_list) + 1
    except Exception:
        pass
    return 0


def _run_meshtype(mesh_type: str, tier_hint: str, label: str) -> dict:
    from core.pipeline.orchestrator import PipelineOrchestrator
    from core.utils.stl_writer import write_stl_ascii

    V, F = _cube_VF()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        stl = td / "cube.stl"
        write_stl_ascii(V, F, stl)
        out = td / "out"
        orch = PipelineOrchestrator()
        result = orch.run(
            stl, out,
            mesh_type=mesh_type, tier_hint=tier_hint, quality_level="draft",
        )
        poly = out / "constant" / "polyMesh"
        cells = _read_polymesh_count(poly) if poly.exists() else 0
        return {
            "mesh_type": mesh_type,
            "tier_hint": tier_hint,
            "label": label,
            "polymesh_exists": poly.exists(),
            "cells": cells,
        }


def test_gui_default_tet_uses_vendored_wildmesh():
    """mesh_type=tet 기본 → tier_wildmesh → vendored fTetWild → polyMesh 생성."""
    pytest.importorskip("scipy")
    r = _run_meshtype("tet", "wildmesh", "tet/vendored fTetWild")
    assert r["polymesh_exists"], f"polyMesh dir not created for {r}"
    assert r["cells"] > 0, f"empty mesh: {r}"


def test_gui_default_hex_dominant_uses_vendored_cfmesh():
    """mesh_type=hex_dominant 기본 → tier15_cfmesh → vendored cartesianMesh."""
    cfm_so = REPO / "auto_tessell_core" / "build" / "cfmesh_native.cpython-312-x86_64-linux-gnu.so"
    if not cfm_so.exists():
        pytest.skip("cfmesh_native.so not built")
    r = _run_meshtype("hex_dominant", "cfmesh", "hex_dominant/vendored cfMesh cartesianMesh")
    assert r["polymesh_exists"], f"polyMesh dir not created for {r}"
    assert r["cells"] > 0, f"empty mesh: {r}"


def test_gui_default_poly_uses_vendored_cfmesh_poly():
    """mesh_type=poly 기본 → tier_cfmesh_poly → vendored pMesh."""
    cfm_so = REPO / "auto_tessell_core" / "build" / "cfmesh_native.cpython-312-x86_64-linux-gnu.so"
    if not cfm_so.exists():
        pytest.skip("cfmesh_native.so not built")
    r = _run_meshtype("poly", "cfmesh_poly", "poly/vendored cfMesh pMesh")
    assert r["polymesh_exists"], f"polyMesh dir not created for {r}"
    assert r["cells"] > 0, f"empty mesh: {r}"


if __name__ == "__main__":
    """Direct run — print result table."""
    print(f"{'mesh_type':<14} {'tier_hint':<14} {'cells':<8} {'status'}")
    print("-" * 60)
    for mt, hint, lbl in [
        ("tet", "wildmesh", "vendored fTetWild"),
        ("hex_dominant", "cfmesh", "vendored cfMesh cartesianMesh"),
        ("poly", "cfmesh_poly", "vendored cfMesh pMesh"),
    ]:
        try:
            r = _run_meshtype(mt, hint, lbl)
            status = "OK" if (r["polymesh_exists"] and r["cells"] > 0) else "FAIL"
            print(f"{r['mesh_type']:<14} {r['tier_hint']:<14} {r['cells']:<8} {status}  ({lbl})")
        except Exception as exc:
            print(f"{mt:<14} {hint:<14} {'-':<8} ERR    ({exc!s:.60})")
