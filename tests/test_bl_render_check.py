"""원격 SSH 에서도 GUI BL 시각 검증 — Xvfb + PyVista offscreen 렌더 → PNG.

실행:
    xvfb-run -s '-screen 0 1280x1024x24' python3 tests/test_bl_render_check.py

산출물:
    /tmp/bl_render/01_outer_surface.png   ← GUI default 렌더 (cube 외벽만)
    /tmp/bl_render/02_clip_x.png          ← x>0.5 부분 잘라내고 단면 노출
    /tmp/bl_render/03_slice_x.png         ← x=0.5 단면 (BL 3 layer 가시)
    /tmp/bl_render/04_bl_only.png         ← WEDGE prism cells 만 분리
"""
from __future__ import annotations
import os
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import sys, tempfile, json
from pathlib import Path
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

OUT = Path("/tmp/bl_render")
OUT.mkdir(parents=True, exist_ok=True)


def _build_mesh(stl: Path, n_layers: int = 3) -> Path:
    from core.pipeline.orchestrator import PipelineOrchestrator
    case = Path(tempfile.mkdtemp(prefix="bl_render_"))
    PipelineOrchestrator().run(
        input_path=stl, output_dir=case,
        mesh_type="tet", quality_level="draft", write_of_case=False,
        tier_specific_params={
            "boundary_layers_enabled": True,
            "cfmesh_bl_n_layers": int(n_layers),
            "cfmesh_bl_thickness_ratio": 1.2,
        },
    )
    foam = case / "case.foam"; foam.touch()
    return foam


def _render(mesh, out_path: Path, *, view: str = "iso",
            color: str = "lightgray", title: str = "") -> None:
    import pyvista as pv
    pv.OFF_SCREEN = True
    pl = pv.Plotter(off_screen=True, window_size=(1024, 768))
    pl.set_background("#ffffff")
    pl.add_mesh(mesh, show_edges=True, color=color,
                edge_color="black", line_width=0.5)
    if view == "iso":
        pl.camera_position = "iso"
    elif view == "yz":
        pl.camera_position = "yz"
    elif view == "xy":
        pl.camera_position = "xy"
    pl.add_axes()
    if title:
        pl.add_text(title, position="upper_left", font_size=14, color="black")
    pl.screenshot(str(out_path))
    pl.close()
    print(f"  saved: {out_path}")


def main(n_layers: int = 3) -> int:
    stl = _ROOT / "test_cube.stl"
    if not stl.exists():
        print(f"[ERR] {stl} 없음"); return 1
    print(f"\n=== BL n_layers = {n_layers} ===")
    foam = _build_mesh(stl, n_layers)
    print(f"polyMesh: {foam.parent}/constant/polyMesh")

    import pyvista as pv
    mesh = pv.OpenFOAMReader(str(foam)).read()
    block0 = mesh.GetBlock(0)
    n_cells = block0.n_cells
    print(f"\nvolume cells: {n_cells}")
    cell_types = list(block0.celltypes)
    from collections import Counter
    ct = Counter(cell_types)
    TYPE = {10: "TETRA", 12: "HEX", 13: "WEDGE", 42: "POLY"}
    type_summary = {TYPE.get(k, f"type{k}"): v for k, v in ct.items()}
    print(f"cell types: {type_summary}")

    n_wedge = ct.get(13, 0)
    print(f"\nWEDGE (BL prism) cells: {n_wedge}")

    # WEDGE 만 추출.
    wedge_idx = np.where(np.array(cell_types) == 13)[0]
    bl_mesh = block0.extract_cells(wedge_idx) if len(wedge_idx) > 0 else None

    # 1) GUI default — 외곽 surface
    surface = block0.extract_surface()
    _render(surface, OUT / "01_outer_surface.png",
            view="iso", color="lightgray",
            title=f"01: Outer surface (GUI default) — {surface.n_cells} faces")

    # 2) Clip x>0.5 — 내부 노출
    clipped = block0.clip(normal="x", origin=(0.5, 0.5, 0.5))
    clip_surf = clipped.extract_surface()
    _render(clip_surf, OUT / "02_clip_x.png",
            view="iso", color="lightblue",
            title=f"02: Clip x>0.5 (interior cells visible) — n_cells={clipped.n_cells}")

    # 3) Slice x=0.5 — 단면 직접
    sliced = block0.slice(normal="x", origin=(0.5, 0.5, 0.5))
    _render(sliced, OUT / "03_slice_x.png",
            view="yz", color="white",
            title=f"03: Slice x=0.5 — BL rings should be visible — n_cells={sliced.n_cells}")

    # 4) WEDGE only
    if bl_mesh is not None:
        bl_surf = bl_mesh.extract_surface()
        _render(bl_surf, OUT / "04_bl_only.png",
                view="iso", color="orange",
                title=f"04: BL prism cells only (WEDGE) — {n_wedge} cells = should be {n_layers}×wall_faces")

    # 5) Slice clip x>0.5 — 단면 + edges
    pl = pv.Plotter(off_screen=True, window_size=(1024, 768))
    pl.set_background("#ffffff")
    pl.add_mesh(clipped, show_edges=True, color="lightyellow",
                edge_color="black", line_width=0.4, opacity=0.95)
    pl.camera_position = "iso"
    pl.add_axes()
    pl.add_text(f"05: Volume cut x>0.5 (전체 셀 + edges) — {n_layers} BL layer 가시 확인용",
                position="upper_left", font_size=14, color="black")
    pl.screenshot(str(OUT / "05_volume_cut.png"))
    pl.close()
    print(f"  saved: {OUT}/05_volume_cut.png")

    # JSON 진단
    diag = {
        "n_layers_requested": n_layers,
        "total_cells": n_cells,
        "tet": ct.get(10, 0),
        "wedge_prism": n_wedge,
        "polyhedron": ct.get(42, 0),
        "expected_wedge": "n_wall_faces × n_layers",
    }
    (OUT / "diag.json").write_text(json.dumps(diag, indent=2))
    print(f"\n진단:\n{json.dumps(diag, indent=2)}")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    sys.exit(main(n_layers=n))
