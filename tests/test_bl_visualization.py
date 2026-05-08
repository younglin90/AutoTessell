"""GUI 가 폴리메시를 어떻게 렌더하는지 — BL 3 layer 가 화면에 보이는지 검증.

PyVista 가 OpenFOAM polyMesh 를 어떻게 변환하는지, slice 후 BL prism 셀이
보이는지 자동으로 확인. 결과는 /tmp/bl_check_*.png 로 저장.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import sys
import tempfile
from pathlib import Path
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    stl = _ROOT / "test_cube.stl"
    if not stl.exists():
        print(f"[ERR] {stl} not found"); return 1

    from core.pipeline.orchestrator import PipelineOrchestrator

    case_dir = Path(tempfile.mkdtemp(prefix="bl_check_"))
    print(f"case dir: {case_dir}")

    PipelineOrchestrator().run(
        input_path=stl, output_dir=case_dir,
        mesh_type="tet", quality_level="draft",
        write_of_case=False,
        tier_specific_params={
            "boundary_layers_enabled": True,
            "cfmesh_bl_n_layers": 3,
            "cfmesh_bl_thickness_ratio": 1.2,
        },
    )

    # GUI 와 동일하게 PyVista OpenFOAMReader 로 읽기.
    foam_file = case_dir / "case.foam"
    foam_file.touch()
    import pyvista as pv
    pv.OFF_SCREEN = True

    reader = pv.OpenFOAMReader(str(foam_file))
    mesh = reader.read()

    print(f"\nMultiBlock n_blocks = {mesh.n_blocks}")
    block0 = mesh.GetBlock(0)
    if block0 is not None:
        print(f"Block 0 (volume cells): n_cells={block0.n_cells} n_points={block0.n_points}")
        # cell type histogram
        from collections import Counter
        cell_types = list(block0.celltypes) if hasattr(block0, "celltypes") else []
        ct_count = Counter(cell_types)
        TYPE_NAME = {10: "TETRA", 12: "HEX", 13: "WEDGE", 42: "POLYHEDRON"}
        print(f"  cell types:")
        for ct, n in sorted(ct_count.items(), key=lambda kv: -kv[1]):
            print(f"    {TYPE_NAME.get(ct, f'type{ct}')} ({ct}) = {n}")

    # GUI 가 하는 default = block0.extract_surface()
    print("\n--- GUI default: block0.extract_surface() ---")
    surface = block0.extract_surface()
    print(f"surface n_cells={surface.n_cells} (= 외곽 면만)")

    # Default render
    pl = pv.Plotter(off_screen=True, window_size=(800, 600))
    pl.add_mesh(surface, show_edges=True, color="lightgray", line_width=0.5)
    pl.camera_position = "iso"
    pl.add_axes()
    out1 = "/tmp/bl_check_default_surface.png"
    pl.screenshot(out1)
    pl.close()
    print(f"  saved: {out1}")

    # Slice view (X=0.5)
    print("\n--- slice X=0.5 ---")
    pl = pv.Plotter(off_screen=True, window_size=(800, 600))
    sliced = block0.slice(normal="x", origin=(0.5, 0.5, 0.5))
    print(f"sliced n_cells={sliced.n_cells}")
    pl.add_mesh(sliced, show_edges=True, color="white", line_width=0.5,
                edge_color="black")
    pl.camera_position = "yz"
    pl.add_axes()
    out2 = "/tmp/bl_check_slice_x.png"
    pl.screenshot(out2)
    pl.close()
    print(f"  saved: {out2}")

    # Clip view (clip half to expose interior)
    print("\n--- clip x>0.5 (interior 보이게) ---")
    pl = pv.Plotter(off_screen=True, window_size=(800, 600))
    clipped = block0.clip(normal="x", origin=(0.5, 0.5, 0.5))
    print(f"clipped n_cells={clipped.n_cells}")
    surf2 = clipped.extract_surface()
    pl.add_mesh(surf2, show_edges=True, color="lightblue", line_width=0.5,
                edge_color="black")
    pl.camera_position = "iso"
    pl.add_axes()
    out3 = "/tmp/bl_check_clip_x.png"
    pl.screenshot(out3)
    pl.close()
    print(f"  saved: {out3}")

    # 거리 기반 BL 셀 식별 — wall 에서 0.1 이내 cell 만
    print("\n--- BL cells only (wall distance < 0.1) ---")
    pl = pv.Plotter(off_screen=True, window_size=(800, 600))
    centers = np.asarray(block0.cell_centers().points)
    on_wall = ((np.abs(centers) < 0.005) | (np.abs(centers - 1.0) < 0.005)).any(axis=1)
    near_wall = ((centers < 0.1) | (centers > 0.9)).any(axis=1)
    bl_mask = near_wall
    bl_idx = np.where(bl_mask)[0]
    print(f"cells near wall (<0.1): {len(bl_idx)} (전체 {block0.n_cells})")
    if len(bl_idx) > 0:
        bl_only = block0.extract_cells(bl_idx)
        bl_surf = bl_only.extract_surface()
        pl.add_mesh(bl_surf, show_edges=True, color="orange", line_width=0.3,
                    edge_color="darkred")
        pl.camera_position = "iso"
        pl.add_axes()
        out4 = "/tmp/bl_check_bl_cells_only.png"
        pl.screenshot(out4)
        pl.close()
        print(f"  saved: {out4}")

    print("\n\n[요약]")
    print(f"  block0 volume cells = {block0.n_cells}")
    print(f"  surface only        = {surface.n_cells} (GUI default)")
    print(f"  near-wall cells     = {len(bl_idx)}")
    print(f"\n  화면에 BL 3 layer 가 보이려면:")
    print(f"  1) Slice/Clip 모드 활성화 (단순 surface 렌더는 외벽만)")
    print(f"  2) {out2} 또는 {out3} 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
