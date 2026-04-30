"""K5 / beta2637 — mesh quality histogram dump.

생성된 polyMesh 의 quality distribution 을 ASCII histogram 으로 dump.
디버깅 / 시각화 / report 용.

Usage:
    python3 scripts/dump_quality_histogram.py path/to/polyMesh
    python3 scripts/dump_quality_histogram.py path/to/case  # case/constant/polyMesh 자동.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bin_quality(qs, n_bins: int = 20) -> list[tuple[float, float, int]]:
    """quality array → bin (lo, hi, count) list."""
    import numpy as np
    qs = np.asarray(qs, dtype=np.float64)
    if qs.size == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    counts, _ = np.histogram(qs, bins=edges)
    return [
        (float(edges[i]), float(edges[i + 1]), int(counts[i]))
        for i in range(n_bins)
    ]


def _ascii_bar(count: int, max_count: int, width: int = 40) -> str:
    if max_count == 0:
        return ""
    n_filled = int((count / max_count) * width)
    return "#" * n_filled + " " * (width - n_filled)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="polyMesh 또는 case 디렉터리")
    ap.add_argument("--n-bins", type=int, default=20)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np

    p = Path(args.path)
    pm_dir = p
    if (p / "constant" / "polyMesh").exists():
        pm_dir = p / "constant" / "polyMesh"

    if not pm_dir.exists():
        print(f"[ERR] polyMesh not found: {pm_dir}", file=sys.stderr)
        return 1

    # poly_mesh_reader 가 없으므로 직접 읽기 (tet 또는 hex 가정).
    # case_dir 의 _work 또는 metadata 에서 추출 — 실용적으로 그냥
    # quality.json 또는 quality stats 가 있으면 사용.
    quality_file = pm_dir.parent.parent / "_work" / "native_bl_quality.json"
    if not quality_file.exists():
        quality_file = pm_dir.parent.parent / "native_bl_quality.json"

    qs: list[float] = []
    if quality_file.exists():
        import json
        try:
            qd = json.loads(quality_file.read_text(encoding="utf-8"))
            # nested 된 quality histogram 또는 prism aspect.
            for k in ("quality", "qualities", "tet_quality"):
                if k in qd and isinstance(qd[k], list):
                    qs = [float(x) for x in qd[k]]
                    break
        except Exception:
            pass

    if not qs:
        # No JSON — synthesize from points + tets if .npy 있다면.
        print("[WARN] no quality data — try synthesize via native_tet quality.")
        print(f"      checked: {quality_file}")
        return 2

    print(f"\n[QUALITY HISTOGRAM] n_cells={len(qs)}, n_bins={args.n_bins}")
    print(f"  min={min(qs):.4f}, max={max(qs):.4f}, mean={sum(qs)/len(qs):.4f}")
    print()
    bins = _bin_quality(qs, args.n_bins)
    max_count = max(b[2] for b in bins) if bins else 0
    for lo, hi, count in bins:
        bar = _ascii_bar(count, max_count, width=40)
        pct = 100.0 * count / len(qs) if len(qs) > 0 else 0.0
        print(f"  [{lo:.3f}-{hi:.3f}) {count:6d} ({pct:5.1f}%) {bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
