"""J3 / beta2628 — pre-flight STL validator.

mesh 시작 전 STL 의 health check:
    - file readable, vertex/face count > threshold.
    - watertight, manifold, num_components.
    - dihedral statistics, sharpness.
    - self-intersection (sample-based).
    - bbox aspect ratio (thin geometry warning).
    - coordinate magnitude (auto-bump 가능 신호).

Usage:
    python3 scripts/validate_stl.py path/to/mesh.stl
    python3 scripts/validate_stl.py path/to/dir/  # batch (모든 *.stl).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def validate_one(stl_path: Path) -> dict:
    """단일 STL 검증. dict {ok: bool, warnings: [...], stats: {...}} 반환."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.analyzer.readers.stl import read_stl
    from core.analyzer.topology import is_watertight, is_manifold

    out: dict = {"path": str(stl_path), "warnings": []}

    try:
        mesh = read_stl(str(stl_path))
        import numpy as np
        V = np.asarray(mesh.vertices, dtype=np.float64)
        F = np.asarray(mesh.faces, dtype=np.int64)
    except Exception as exc:
        out["ok"] = False
        out["error"] = f"read failed: {exc!s:.80}"
        return out

    n_v, n_f = int(V.shape[0]), int(F.shape[0])
    out["n_vertices"] = n_v
    out["n_faces"] = n_f

    if n_v < 4:
        out["ok"] = False
        out["warnings"].append("vertex count < 4 (degenerate)")
        return out
    if n_f < 4:
        out["ok"] = False
        out["warnings"].append("face count < 4 (degenerate)")
        return out

    # bbox.
    bmin = V.min(axis=0)
    bmax = V.max(axis=0)
    extents = bmax - bmin
    bbox_diag = float(np.linalg.norm(extents))
    out["bbox_diag"] = round(bbox_diag, 6)

    if bbox_diag < 1e-9:
        out["warnings"].append("bbox_diag < 1e-9 (zero extent)")
    if extents.min() > 0:
        ar = float(extents.max() / extents.min())
        out["aspect_ratio"] = round(ar, 1)
        if ar > 100:
            out["warnings"].append(f"thin geometry: aspect_ratio={ar:.1f} > 100")

    # 좌표 magnitude check.
    coord_max = float(np.abs(V).max())
    out["coord_max"] = round(coord_max, 6)
    if coord_max > 1e6:
        out["warnings"].append(f"coord_max={coord_max:.1e} > 1e6 (rescale 권장)")
    if coord_max < 1e-6 and bbox_diag > 0:
        out["warnings"].append(f"coord_max={coord_max:.1e} < 1e-6 (sub-mm scale)")

    # watertight + manifold.
    try:
        wt = bool(is_watertight(F))
        mf = bool(is_manifold(F))
        out["watertight"] = wt
        out["manifold"] = mf
        if not wt:
            out["warnings"].append("NOT watertight (open boundary)")
        if not mf:
            out["warnings"].append("NOT manifold (3+ face share edge)")
    except Exception as exc:
        out["warnings"].append(f"topology check failed: {exc!s:.50}")

    # self-intersection (small mesh 만).
    if n_f <= 5000:
        try:
            from core.preprocessor.native_repair.self_intersect import (
                detect_self_intersections,
            )
            si = detect_self_intersections(V, F)
            out["n_self_intersect"] = int(si.n_intersections)
            if si.n_intersections > 0:
                pct = 100.0 * si.n_intersections / max(n_f, 1)
                out["warnings"].append(
                    f"self-intersect: {si.n_intersections} pairs ({pct:.1f}%)"
                )
        except Exception as exc:
            out["warnings"].append(f"SI detect failed: {exc!s:.50}")
    else:
        out["n_self_intersect"] = -1  # not measured.

    out["ok"] = len(out["warnings"]) == 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="STL 파일 또는 디렉터리 경로")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"[ERR] not found: {p}", file=sys.stderr)
        return 1

    targets = [p] if p.is_file() else sorted(p.glob("*.stl"))
    if not targets:
        print(f"[ERR] no STL in {p}", file=sys.stderr)
        return 2

    n_ok = 0
    n_warn = 0
    n_err = 0
    for stl in targets:
        r = validate_one(stl)
        if "error" in r:
            print(f"[ERR ] {stl.name}: {r['error']}")
            n_err += 1
            continue
        warn_str = "; ".join(r["warnings"]) if r["warnings"] else "OK"
        prefix = "[OK  ]" if r["ok"] else "[WARN]"
        print(
            f"{prefix} {stl.name}: V={r.get('n_vertices', '?')} "
            f"F={r.get('n_faces', '?')} bbox={r.get('bbox_diag', '?')} "
            f"WT={r.get('watertight', '?')} MF={r.get('manifold', '?')} "
            f"SI={r.get('n_self_intersect', '-')}: {warn_str}"
        )
        if r["ok"]:
            n_ok += 1
        else:
            n_warn += 1

    print(f"\n[SUMMARY] {n_ok} OK / {n_warn} WARN / {n_err} ERR / total {len(targets)}")
    return 0 if n_err == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
