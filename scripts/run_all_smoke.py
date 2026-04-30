"""S6 / beta2693 — All-tier smoke test runner.

native_tet/hex/poly 3개 engine 으로 동일 STL 빠른 mesh 시도 → 결과 표.
CI/CD 의 quick smoke 또는 dev iteration 에 사용.

Usage:
    python3 scripts/run_all_smoke.py input.stl
    python3 scripts/run_all_smoke.py input.stl --seed-density 12
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--seed-density", type=int, default=8)
    ap.add_argument("--skip-bl", action="store_true", help="BL 단계 스킵")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import numpy as np
    from core.analyzer.readers.stl import read_stl

    if not args.input.exists():
        print(f"[ERR] not found: {args.input}", file=sys.stderr)
        return 1

    try:
        m = read_stl(str(args.input))
        V = np.asarray(m.vertices, dtype=np.float64)
        F = np.asarray(m.faces, dtype=np.int64)
    except Exception as exc:
        print(f"[ERR] read: {exc}", file=sys.stderr)
        return 2

    print(f"\n[ALL-TIER SMOKE] {args.input.name}")
    print(f"  V={V.shape[0]}, F={F.shape[0]}, seed_density={args.seed_density}\n")
    print(f"  {'engine':<8} {'success':>8} {'cells':>10} {'grade':>6} {'time':>8}")
    print(f"  {'-'*44}")

    import tempfile
    results = []
    for engine in ("tet", "hex", "poly"):
        t0 = time.perf_counter()
        success = False
        n_cells = 0
        grade = "?"
        try:
            with tempfile.TemporaryDirectory() as td:
                case = Path(td) / "c"
                if engine == "tet":
                    from core.generator.native_tet.mesher import generate_native_tet
                    r = generate_native_tet(V, F, case, seed_density=args.seed_density)
                    success = r.success
                    n_cells = int(r.tets.shape[0]) if r.tets is not None else 0
                    grade = str(getattr(r, "quality_grade", "?"))
                elif engine == "hex":
                    from core.generator.native_hex.mesher import generate_native_hex
                    r = generate_native_hex(V, F, case, seed_density=args.seed_density)
                    success = r.success
                    n_cells = int(getattr(r, "n_cells", 0))
                    grade = str(getattr(r, "quality_grade", "?"))
                else:
                    from core.generator.native_poly.voronoi import generate_native_poly_voronoi
                    r = generate_native_poly_voronoi(V, F, case, seed_density=args.seed_density)
                    success = r.success
                    n_cells = int(getattr(r, "n_cells", 0))
                    grade = str(getattr(r, "quality_grade", "?"))
        except Exception:
            pass
        t = time.perf_counter() - t0
        results.append((engine, success, n_cells, grade, t))
        print(f"  {engine:<8} {'✓' if success else '✗':>8} {n_cells:>10,} {grade:>6} {t:>7.2f}s")

    # 합계 / overall.
    n_ok = sum(1 for _, s, _, _, _ in results if s)
    print(f"\n  {n_ok}/{len(results)} engines succeeded")
    return 0 if n_ok == len(results) else 3


if __name__ == "__main__":
    sys.exit(main())
