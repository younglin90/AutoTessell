"""Headless GUI BL propagation test (standalone, no pytest-qt).

목적: GUI BL 위젯값이 → tier_specific_params 까지 정확히 전달되는지 사용자
클릭 없이 검증. polyMesh 까지 검증은 별도 함수로 분리 (느림 — opt-in).

실행:
    QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true \
        python3 tests/test_gui_bl_propagation.py [--full]

옵션:
    --full   실제 orchestrator 까지 호출해서 polyMesh BL 검증 (~60s).
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("VTK_USE_X", "0")

import sys
import tempfile
from pathlib import Path
import numpy as np

# 프로젝트 루트.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# main_window 가 mesh_viewer 를 import 할 때 PyVista plotter 가 X 없이 segfault.
# stub 으로 차단.
import desktop.qt_app.mesh_viewer as _mv_mod  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402


class _StubMeshViewer(QWidget):
    mesh_stats_computed = None
    def __init__(self, *a, **kw):
        super().__init__()
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **kw: None

_mv_mod.MeshViewerWidget = _StubMeshViewer  # type: ignore[assignment]
_mv_mod.InteractiveMeshViewer = _StubMeshViewer  # type: ignore[assignment]
_mv_mod.StaticMeshViewer = _StubMeshViewer  # type: ignore[assignment]


# 윈도우 인스턴스를 모듈 레벨에 캐싱 — 매 케이스마다 새로 만들면 느리고 hang.
_WIN_CACHE: dict = {"win": None, "app": None}


def _get_window():
    if _WIN_CACHE["win"] is None:
        from PySide6.QtWidgets import QApplication
        _WIN_CACHE["app"] = QApplication.instance() or QApplication(sys.argv)
        from desktop.qt_app.main_window import AutoTessellWindow
        _WIN_CACHE["win"] = AutoTessellWindow()
        _WIN_CACHE["win"].show()
    return _WIN_CACHE["win"]


def _capture_tier_params(stl_path: Path, *,
                         bl_on: bool, n_layers: int, ratio: float,
                         first_thickness: float,
                         mesh_type: str = "tet") -> dict:
    """Window 가져와서 위젯 값만 재설정 후 _on_run_clicked → tier_params 캡처."""
    win = _get_window()
    win.set_input_path(stl_path)
    win._mesh_type = mesh_type

    win._bl_check.setChecked(bl_on)
    if hasattr(win, "_cfm_bl_layers_spin"):
        win._cfm_bl_layers_spin.setValue(n_layers)
    if hasattr(win, "_cfm_bl_ratio_spin"):
        win._cfm_bl_ratio_spin.setValue(ratio)
    if hasattr(win, "_cfm_bl_first_spin"):
        win._cfm_bl_first_spin.setValue(first_thickness)

    captured: dict = {}
    import desktop.qt_app.pipeline_worker as _pw
    OrigWorker = _pw.PipelineWorker

    class _SpyWorker:
        def __init__(self, *args, **kwargs):
            captured["tsp"] = dict(kwargs.get("tier_specific_params") or {})
            captured["mesh_type"] = kwargs.get("mesh_type")
            captured["quality_level"] = kwargs.get("quality_level")
            raise RuntimeError("__SPY_BREAK__")

    _pw.PipelineWorker = _SpyWorker  # type: ignore[assignment]
    try:
        try:
            win._on_run_clicked()
        except RuntimeError as exc:
            if "__SPY_BREAK__" not in str(exc):
                raise
    finally:
        _pw.PipelineWorker = OrigWorker  # type: ignore[assignment]
    return captured


def _check(name: str, got, want, fmt=str) -> int:
    """간단 assertion. 실패시 1 반환, 성공시 0."""
    ok = (got == want) if not isinstance(want, float) else abs(float(got) - want) < 1e-6
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: got={fmt(got)}, want={fmt(want)}")
    return 0 if ok else 1


def main(full: bool = False) -> int:
    stl = _PROJECT_ROOT / "test_cube.stl"
    if not stl.exists():
        print(f"[ERR] test_cube.stl not found: {stl}")
        return 1

    failures = 0
    print("\n" + "=" * 70)
    print(" CASE 1: BL ON, layers=3, ratio=1.2, first=0 (auto)")
    print("=" * 70)
    cap = _capture_tier_params(stl, bl_on=True, n_layers=3, ratio=1.2,
                               first_thickness=0.0)
    tsp = cap.get("tsp") or {}
    print(f"  GUI mesh_type        = {cap.get('mesh_type')}")
    print(f"  GUI quality_level    = {cap.get('quality_level')}")
    print(f"  GUI tier_specific_params:")
    for k, v in sorted(tsp.items()):
        print(f"      {k} = {v}")

    failures += _check("boundary_layers_enabled", tsp.get("boundary_layers_enabled"), True)
    failures += _check("cfmesh_bl_n_layers", tsp.get("cfmesh_bl_n_layers"), 3)
    failures += _check("cfmesh_bl_thickness_ratio", tsp.get("cfmesh_bl_thickness_ratio"), 1.2)

    print("\n" + "=" * 70)
    print(" CASE 2: BL ON, layers=5, ratio=1.3, first=0.005")
    print("=" * 70)
    cap2 = _capture_tier_params(stl, bl_on=True, n_layers=5, ratio=1.3,
                                first_thickness=0.005)
    tsp2 = cap2.get("tsp") or {}
    failures += _check("cfmesh_bl_n_layers", tsp2.get("cfmesh_bl_n_layers"), 5)
    failures += _check("cfmesh_bl_thickness_ratio", tsp2.get("cfmesh_bl_thickness_ratio"), 1.3)
    failures += _check("cfmesh_bl_max_first_layer", tsp2.get("cfmesh_bl_max_first_layer"), 0.005)

    print("\n" + "=" * 70)
    print(" CASE 3: BL OFF (n_layers spin 값 무시 확인)")
    print("=" * 70)
    cap3 = _capture_tier_params(stl, bl_on=False, n_layers=3, ratio=1.2,
                                first_thickness=0.0)
    tsp3 = cap3.get("tsp") or {}
    print(f"  GUI tier_specific_params (BL):")
    for k in sorted(tsp3.keys()):
        if "bl" in k.lower() or "layer" in k.lower():
            print(f"      {k} = {tsp3[k]}")
    failures += _check("cfmesh_bl_n_layers (BL OFF)", tsp3.get("cfmesh_bl_n_layers"), 0)
    failures += _check("boundary_layers_enabled (BL OFF)", tsp3.get("boundary_layers_enabled"), False)

    if full:
        print("\n" + "=" * 70)
        print(" CASE 1 FULL: orchestrator 실행해서 polyMesh BL 깊이 측정")
        print("=" * 70)
        from core.pipeline.orchestrator import PipelineOrchestrator
        from core.utils.polymesh_reader import (
            parse_foam_points, parse_foam_boundary,
        )
        with tempfile.TemporaryDirectory() as td:
            case = Path(td) / "case"
            tsp_full = dict(tsp)
            PipelineOrchestrator().run(
                input_path=stl, output_dir=case, mesh_type="tet",
                quality_level="draft", write_of_case=False,
                tier_specific_params=tsp_full,
            )
            pdir = case / "constant" / "polyMesh"
            pts = np.array(parse_foam_points(pdir / "points"))
            bnd = parse_foam_boundary(pdir / "boundary")
            n_wall_faces = sum(
                int(p["nFaces"]) for p in bnd
                if "wall" in str(p["name"]).lower()
                and "bl_internal" not in str(p["name"]).lower()
            )
            on_cube = ((np.abs(pts) < 1e-6) | (np.abs(pts - 1.0) < 1e-6)).any(axis=1)
            int_pts = pts[~on_cube]
            from scipy.spatial import cKDTree
            d, _ = cKDTree(pts[on_cube]).query(int_pts)
            d_unique = np.unique(np.round(d[d < 0.20], 4))
            bl_d = d_unique[d_unique < 0.15]
            print(f"  n_wall_faces       = {n_wall_faces}")
            print(f"  distinct BL layers = {len(bl_d)}")
            print(f"  BL distances       = {bl_d.tolist()[:6]}")
            print(f"  total BL thickness = {float(bl_d[-1]) if len(bl_d) else 0.0:.5f}")
            if len(bl_d) < 3:
                print(f"  [FAIL] distinct BL layer count < 3"); failures += 1
            elif len(bl_d) > 0 and float(bl_d[-1]) < 0.01:
                print(f"  [FAIL] total BL thickness < 1% of cube edge"); failures += 1
            else:
                print(f"  [PASS] BL 가시성 OK")

    print("\n" + "=" * 70)
    if failures == 0:
        print(" [PASS] GUI BL 파라미터 → tier_specific_params 정상 전파")
        print("=" * 70)
        return 0
    print(f" [FAIL] {failures} 검증 실패")
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main(full="--full" in sys.argv))
