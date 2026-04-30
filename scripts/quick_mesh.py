"""O3 / beta2662 — Single-line native mesh quick CLI.

STL → native_tet/hex/poly 한 줄로. 디버깅 / quick test 용 — 전체 5-agent
파이프라인 거치지 않고 직접 generator 만 호출.

Usage:
    python3 scripts/quick_mesh.py input.stl --engine tet -o ./out
    python3 scripts/quick_mesh.py input.stl --engine hex -o ./out --seed-density 12
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument(
        "--engine", "-e",
        choices=["tet", "hex", "poly"],
        default="tet",
    )
    ap.add_argument("-o", "--output", type=Path, default=Path("./_quick_mesh_out"))
    ap.add_argument("--seed-density", type=int, default=8)
    ap.add_argument("--quality", action="store_true", help="quality stats 표시")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    from core.analyzer.readers.stl import read_stl
    import numpy as np

    t0 = time.perf_counter()
    print(f"[1/3] Read {args.input}")
    try:
        mesh = read_stl(str(args.input))
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
    except Exception as exc:
        print(f"[ERR] read: {exc}", file=sys.stderr)
        return 1
    print(f"      V={V.shape[0]}, F={F.shape[0]}")

    args.output.mkdir(parents=True, exist_ok=True)

    print(f"[2/3] Generate {args.engine} mesh (seed_density={args.seed_density})")
    t1 = time.perf_counter()
    if args.engine == "tet":
        from core.generator.native_tet.mesher import generate_native_tet
        r = generate_native_tet(
            V, F, args.output / "case",
            seed_density=args.seed_density,
            enable_phase_a=True, enable_phase_c=True,
            enable_amips_smooth=True,
        )
    elif args.engine == "hex":
        from core.generator.native_hex.mesher import generate_native_hex
        r = generate_native_hex(
            V, F, args.output / "case",
            seed_density=args.seed_density,
            snap_boundary=True, snap_iterations=2,
        )
    else:  # poly
        from core.generator.native_poly.voronoi import generate_native_poly_voronoi
        r = generate_native_poly_voronoi(
            V, F, args.output / "case",
            seed_density=args.seed_density,
            n_lloyd=2, auto_escalate=True,
        )

    elapsed = time.perf_counter() - t1
    n_cells = int(getattr(r, "n_cells", 0) or getattr(r, "n_tets", 0))
    grade = str(getattr(r, "quality_grade", "?"))
    print(f"      success={r.success}, n_cells={n_cells}, grade={grade}, t={elapsed:.2f}s")

    if args.quality and args.engine == "tet" and r.success and r.tets is not None:
        print(f"[3/3] Quality stats")
        try:
            from core.analyzer.volume_stats import compute_tet_stats
            pts = np.asarray(r.tet_points, dtype=np.float64)
            tets = np.asarray(r.tets, dtype=np.int64)
            qs = compute_tet_stats(pts, tets, n_bins=10)
            print(f"      min={qs.quality_min:.3f}, mean={qs.quality_mean:.3f}, "
                  f"p5={qs.quality_p5:.3f}, p50={qs.quality_p50:.3f}, p95={qs.quality_p95:.3f}")
            print(f"      n_negative={qs.n_negative_volume}, vol_total={qs.volume_total:.4e}")
        except Exception as exc:
            print(f"      quality calc failed: {exc}")

    total = time.perf_counter() - t0
    print(f"\n[DONE] total {total:.2f}s, output: {args.output}")
    return 0 if r.success else 2


if __name__ == "__main__":
    sys.exit(main())
