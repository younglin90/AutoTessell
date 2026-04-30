"""P6 / beta2672 — quality threshold 이하 cell 제외 export.

native_tet 결과의 q < threshold 인 cell 만 골라 별도 .vtu 로 export.
sliver 디버깅 / paraview 시각화 용.

Usage:
    python3 scripts/export_filtered_quality.py case_dir -o sliver.vtu --threshold 0.1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=0.1)
    ap.add_argument("--mode", choices=["below", "above"], default="below")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import numpy as np

    # Try to load tet_points + tets from case _work.
    work = args.case_dir / "_work"
    pts_npy = work / "tet_points.npy"
    tets_npy = work / "tets.npy"
    if not pts_npy.exists() or not tets_npy.exists():
        print(f"[ERR] tet_points.npy 또는 tets.npy 없음: {work}", file=sys.stderr)
        print(f"      native_tet 가 _work 에 결과를 dump 하도록 env 설정 필요.")
        return 1

    pts = np.load(pts_npy)
    tets = np.load(tets_npy)
    if tets.size == 0:
        print(f"[ERR] empty tets array")
        return 2

    from core.analyzer.volume_stats import compute_tet_stats
    stats = compute_tet_stats(pts, tets)
    print(f"[INFO] n_cells={stats.n_cells}, q range [{stats.quality_min:.3f}, {stats.quality_max:.3f}]")

    # quality 재계산 (vectorized).
    p0 = pts[tets[:, 0]]; p1 = pts[tets[:, 1]]
    p2 = pts[tets[:, 2]]; p3 = pts[tets[:, 3]]
    e0 = p1 - p0; e1 = p2 - p0; e2 = p3 - p0
    e3 = p2 - p1; e4 = p3 - p1; e5 = p3 - p2
    e_sq_sum = (
        (e0 ** 2).sum(1) + (e1 ** 2).sum(1) + (e2 ** 2).sum(1)
        + (e3 ** 2).sum(1) + (e4 ** 2).sum(1) + (e5 ** 2).sum(1)
    )
    vol6 = (np.cross(e1, e2) * e0).sum(1)
    vol = np.abs(vol6) / 6.0
    qs = np.where(
        e_sq_sum > 1e-30,
        np.clip(12.0 * ((3.0 * vol) ** (2.0 / 3.0)) / e_sq_sum, 0.0, 1.0),
        0.0,
    )

    # filter.
    if args.mode == "below":
        mask = qs < args.threshold
    else:
        mask = qs >= args.threshold
    n_kept = int(mask.sum())

    if n_kept == 0:
        print(f"[INFO] no cells match (mode={args.mode}, threshold={args.threshold})")
        return 0

    filtered_tets = tets[mask]
    print(f"[INFO] filtered: {n_kept} / {tets.shape[0]} cells (mode={args.mode})")

    # Build minimal VTU output (tet only).
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        n_pts = pts.shape[0]
        n_c = filtered_tets.shape[0]
        f.write('<?xml version="1.0"?>\n')
        f.write('<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n')
        f.write('  <UnstructuredGrid>\n')
        f.write(f'    <Piece NumberOfPoints="{n_pts}" NumberOfCells="{n_c}">\n')
        f.write('      <Points>\n')
        f.write('        <DataArray type="Float64" NumberOfComponents="3" format="ascii">\n')
        for p in pts:
            f.write(f'          {p[0]:.10e} {p[1]:.10e} {p[2]:.10e}\n')
        f.write('        </DataArray>\n')
        f.write('      </Points>\n')
        f.write('      <Cells>\n')
        f.write('        <DataArray type="Int64" Name="connectivity" format="ascii">\n')
        f.write('          ' + ' '.join(map(str, filtered_tets.ravel())) + '\n')
        f.write('        </DataArray>\n')
        f.write('        <DataArray type="Int64" Name="offsets" format="ascii">\n')
        offsets = np.arange(4, 4 * n_c + 1, 4)
        f.write('          ' + ' '.join(map(str, offsets)) + '\n')
        f.write('        </DataArray>\n')
        f.write('        <DataArray type="UInt8" Name="types" format="ascii">\n')
        f.write('          ' + ' '.join(['10'] * n_c) + '\n')  # VTK_TETRA = 10.
        f.write('        </DataArray>\n')
        f.write('      </Cells>\n')
        f.write('      <CellData Scalars="quality">\n')
        f.write('        <DataArray type="Float64" Name="quality" format="ascii">\n')
        q_filtered = qs[mask]
        f.write('          ' + ' '.join(f'{float(q):.6e}' for q in q_filtered) + '\n')
        f.write('        </DataArray>\n')
        f.write('      </CellData>\n')
        f.write('    </Piece>\n')
        f.write('  </UnstructuredGrid>\n')
        f.write('</VTKFile>\n')

    print(f"[OK] saved {args.output} ({n_kept} cells)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
