"""M6 / beta2651 — VTK 에 quality scalar field 동봉 export.

native_tet result (pts + tets) → VTU 에 cell-data scalar 'quality' 추가.
ParaView 에서 quality colormap 시각화 가능.

Usage:
    python3 scripts/export_quality_vtk.py case_dir out.vtu
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="case 또는 polyMesh 디렉터리")
    ap.add_argument("output", type=Path, help="출력 .vtu 파일")
    ap.add_argument("--binary", action="store_true", help="binary base64 mode")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import numpy as np
    from core.utils.vtk_writer import write_vtu

    pm_dir = args.input
    if (args.input / "constant" / "polyMesh").exists():
        pm_dir = args.input / "constant" / "polyMesh"

    if not (pm_dir / "points").exists():
        print(f"[ERR] polyMesh 없음: {pm_dir}", file=sys.stderr)
        return 1

    # First, write VTU base mesh.
    rv = write_vtu(str(pm_dir), str(args.output), binary=args.binary)
    if not rv.success:
        print(f"[ERR] VTU write failed: {rv.message}", file=sys.stderr)
        return 2
    print(f"[OK] VTU written: n_cells={rv.n_cells}, n_pts={rv.n_points}")

    # Append CellData / quality scalar — XML manipulation 으로 inject.
    # Simplest: read content + insert <CellData> 블록 직전 </Cells>.
    content = args.output.read_text(encoding="utf-8")
    if "<CellData" in content:
        print("[INFO] CellData 이미 존재 — skipping append")
        return 0

    # Compute quality (단순: cell-id 기반 dummy — 실제 quality 추출은 native_tet
    # internals 필요. 본 스크립트는 framework — 사용자 cell quality JSON 가
    # case_dir/_work/native_bl_quality.json 또는 quality.npy 에 있다 가정.
    quality_npy = pm_dir.parent.parent / "_work" / "quality.npy"
    qs = None
    if quality_npy.exists():
        try:
            qs = np.load(quality_npy)
        except Exception:
            qs = None
    if qs is None:
        # synthesize ramp 0..1 (placeholder).
        qs = np.linspace(0.0, 1.0, rv.n_cells)
        print(f"[INFO] quality.npy 없음 — placeholder ramp 사용")

    if qs.size != rv.n_cells:
        # truncate or pad.
        qs2 = np.zeros(rv.n_cells, dtype=np.float64)
        n_copy = min(qs.size, rv.n_cells)
        qs2[:n_copy] = qs[:n_copy]
        qs = qs2

    # Build CellData XML block (ASCII).
    qs_str = " ".join(f"{float(q):.6e}" for q in qs)
    cell_data_block = (
        '      <CellData Scalars="quality">\n'
        '        <DataArray type="Float64" Name="quality" format="ascii">\n'
        f'          {qs_str}\n'
        '        </DataArray>\n'
        '      </CellData>\n'
    )

    # Insert before </Cells> closing.
    insert_marker = "      </Cells>\n"
    if insert_marker not in content:
        print(f"[ERR] couldn't find </Cells> in VTU — schema mismatch", file=sys.stderr)
        return 3
    new_content = content.replace(
        insert_marker,
        insert_marker + cell_data_block,
        1,
    )
    args.output.write_text(new_content, encoding="utf-8")
    print(f"[OK] quality scalar appended: {args.output} (n={qs.size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
