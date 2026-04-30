"""U2 / beta2703 — mesh I/O format timing micro-bench.

여러 출력 포맷 (vtu / star_ccm_ascii / stl_ascii / stl_binary 등) 의 write 시간을
동일한 (V, F) 입력에 대해 측정. file size + write_s 출력.

Usage:
    python3 scripts/bench_io_formats.py --n_tris 10000 --out /tmp/bench_io
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _gen_sphere(n_tris: int):
    """간단한 sphere triangulation (icosphere subdivision)."""
    import numpy as np

    # icosahedron vertices.
    phi = (1 + 5 ** 0.5) / 2
    V = np.array([
        [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
        [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
        [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1],
    ], dtype=np.float64)
    V = V / np.linalg.norm(V, axis=1, keepdims=True)

    F = np.array([
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ], dtype=np.int64)

    while F.shape[0] < n_tris:
        # 1 subdivision step.
        edge_mid = {}
        new_V = list(V)
        new_F = []
        for tri in F:
            a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
            mids = []
            for u, v in [(a, b), (b, c), (c, a)]:
                key = (min(u, v), max(u, v))
                if key not in edge_mid:
                    m = (V[u] + V[v]) / 2
                    m = m / max(float((m ** 2).sum() ** 0.5), 1e-30)
                    edge_mid[key] = len(new_V)
                    new_V.append(m)
                mids.append(edge_mid[key])
            ab, bc, ca = mids
            new_F.extend([[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]])
        V = np.array(new_V, dtype=np.float64)
        F = np.array(new_F, dtype=np.int64)

    return V, F[:n_tris]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_tris", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=Path("/tmp/bench_io"))
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    V, F = _gen_sphere(args.n_tris)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"\n=== bench_io_formats (V={V.shape[0]} F={F.shape[0]}) ===\n")

    # STL ASCII / binary.
    try:
        from core.utils.stl_writer import write_stl_ascii, write_stl_binary
        for name, fn, ext in [
            ("stl_ascii", write_stl_ascii, ".stl"),
            ("stl_binary", write_stl_binary, ".stl"),
        ]:
            p = args.out / f"out_{name}{ext}"
            t0 = time.perf_counter()
            r = fn(V, F, p)
            dt = time.perf_counter() - t0
            sz = p.stat().st_size if p.exists() else 0
            ok = "OK" if (r.success if hasattr(r, "success") else True) else "FAIL"
            print(f"  {name:<20}  {ok}  write={dt*1000:8.2f}ms  size={sz/1024:8.2f}KB")
    except Exception as exc:
        print(f"  [WARN] stl_writer: {exc}")

    # VTK writer (if accepts surface).
    try:
        from core.utils.vtk_writer import write_vtk_surface
        p = args.out / "out_surface.vtk"
        t0 = time.perf_counter()
        write_vtk_surface(V, F, p)
        dt = time.perf_counter() - t0
        sz = p.stat().st_size if p.exists() else 0
        print(f"  {'vtk_surface':<20}  OK  write={dt*1000:8.2f}ms  size={sz/1024:8.2f}KB")
    except Exception as exc:
        print(f"  [SKIP] vtk_writer: {exc}")

    print(f"\n[OK] outputs → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
