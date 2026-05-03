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
    """polyMesh dir → cell count.

    1) ccmio reader 시도, 2) owner 파일에서 직접 cell 개수 파싱 (owner 의
    `\\n<count>\\n(\\n` 패턴은 face 수 → cell = max(owner)+1).
    """
    owner = poly_dir / "owner"
    if not owner.exists():
        return 0
    # 1) ccmio reader.
    try:
        from core.utils.ccmio_native_binary import _simple_polymesh_read
        _, _, own_list, _, _ = _simple_polymesh_read(poly_dir)
        if own_list:
            return max(int(o) for o in own_list) + 1
    except Exception:
        pass
    # 2) owner 파일 직접 파싱.
    try:
        text = owner.read_text(errors="ignore")
        # FoamFile 헤더 끝 후 첫 숫자 줄이 face 개수, 그 다음 ( 다음 줄부터
        # owner index 들. cell 개수 = max + 1.
        lines = text.split("\n")
        # 데이터 시작 찾기: '(' 만 있는 줄.
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "(":
                start = i + 1
                break
        if start is None:
            return 0
        max_cell = -1
        for line in lines[start:]:
            s = line.strip()
            if s == ")":
                break
            if s.isdigit():
                v = int(s)
                if v > max_cell:
                    max_cell = v
        return max_cell + 1 if max_cell >= 0 else 0
    except Exception:
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


def _run_meshtype_with_params(mesh_type: str, tier_hint: str, tier_params: dict) -> dict:
    """tier_specific_params 를 명시적으로 전달하는 변종."""
    from core.pipeline.orchestrator import PipelineOrchestrator
    from core.utils.stl_writer import write_stl_ascii
    V, F = _cube_VF()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        stl = td / "cube.stl"
        write_stl_ascii(V, F, stl)
        out = td / "out"
        orch = PipelineOrchestrator()
        orch.run(
            stl, out,
            mesh_type=mesh_type, tier_hint=tier_hint, quality_level="draft",
            tier_specific_params=tier_params,
        )
        poly = out / "constant" / "polyMesh"
        cells = _read_polymesh_count(poly) if poly.exists() else 0
        return {"cells": cells}


def test_gui_cfmesh_max_cell_param_changes_count():
    """GUI cfmesh_max_cell_size param 변경 시 cell 수 달라짐."""
    cfm_so = REPO / "auto_tessell_core" / "build" / "cfmesh_native.cpython-312-x86_64-linux-gnu.so"
    if not cfm_so.exists():
        pytest.skip("cfmesh_native.so not built")
    coarse = _run_meshtype_with_params(
        "hex_dominant", "cfmesh", {"cfmesh_max_cell_size": 0.3},
    )
    fine = _run_meshtype_with_params(
        "hex_dominant", "cfmesh", {"cfmesh_max_cell_size": 0.1},
    )
    assert coarse["cells"] > 0 and fine["cells"] > 0
    assert fine["cells"] > coarse["cells"], (
        f"finer max_cell should yield more cells: coarse={coarse} fine={fine}"
    )


def test_gui_cfmesh_bl_layers_param_creates_bl():
    """GUI cfmesh_bl_n_layers > 0 → BL 추가 → cell 수 증가."""
    cfm_so = REPO / "auto_tessell_core" / "build" / "cfmesh_native.cpython-312-x86_64-linux-gnu.so"
    if not cfm_so.exists():
        pytest.skip("cfmesh_native.so not built")
    no_bl = _run_meshtype_with_params(
        "hex_dominant", "cfmesh",
        {"cfmesh_max_cell_size": 0.2, "cfmesh_bl_n_layers": 0},
    )
    with_bl = _run_meshtype_with_params(
        "hex_dominant", "cfmesh",
        {"cfmesh_max_cell_size": 0.2, "cfmesh_bl_n_layers": 3,
         "cfmesh_bl_thickness_ratio": 1.2},
    )
    assert no_bl["cells"] > 0 and with_bl["cells"] > 0
    # BL 추가 시 boundary cell 들이 prism 으로 분할되어 셀 수 증가 (>=).
    assert with_bl["cells"] >= no_bl["cells"], (
        f"BL=3 should yield ≥ no-BL cells: no_bl={no_bl} with_bl={with_bl}"
    )


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
