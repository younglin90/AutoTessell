"""T3 / beta2697 — NPY (V/F) ↔ STL converter.

native_tet 의 _work/{tet_points,tets}.npy 같은 raw arrays → STL surface 변환.
또는 STL → npy (V/F) 분해. 디버깅 / pipeline 단계 격리.

Usage:
    python3 scripts/npy_to_stl.py V.npy F.npy out.stl
    python3 scripts/npy_to_stl.py --reverse in.stl out_V.npy out_F.npy
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("c", type=Path, nargs="?", default=None)
    ap.add_argument("--reverse", action="store_true",
                    help="STL → NPY (a=stl, b=V_npy, c=F_npy)")
    ap.add_argument("--binary", action="store_true",
                    help="STL binary 출력 (forward 모드).")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))

    import numpy as np

    if args.reverse:
        # STL → NPY.
        if args.c is None:
            print("[ERR] --reverse mode 는 3 args 필요 (stl, V_npy, F_npy).", file=sys.stderr)
            return 1
        try:
            from core.analyzer.readers.stl import read_stl
            mesh = read_stl(str(args.a))
            V = np.asarray(mesh.vertices, dtype=np.float64)
            F = np.asarray(mesh.faces, dtype=np.int64)
        except Exception as exc:
            print(f"[ERR] read STL: {exc}", file=sys.stderr)
            return 2
        np.save(str(args.b), V)
        np.save(str(args.c), F)
        print(f"[OK] V.shape={V.shape} → {args.b}")
        print(f"     F.shape={F.shape} → {args.c}")
        return 0
    else:
        # NPY → STL.
        try:
            V = np.load(str(args.a))
            F = np.load(str(args.b))
        except Exception as exc:
            print(f"[ERR] load NPY: {exc}", file=sys.stderr)
            return 1
        out = args.c or args.b.with_suffix(".stl")
        if args.binary:
            from core.utils.stl_writer import write_stl_binary
            r = write_stl_binary(V, F, out)
        else:
            from core.utils.stl_writer import write_stl_ascii
            r = write_stl_ascii(V, F, out)
        if r.success:
            print(f"[OK] {r.n_triangles} tri → {out}")
            return 0
        print(f"[ERR] {r.message}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
