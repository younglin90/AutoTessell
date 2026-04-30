"""N1 / beta2653 — matplotlib quality histogram plot.

case_dir/_work/native_bl_quality.json 또는 quality.npy 의 quality 분포를
matplotlib histogram + grade 색상화로 PNG 저장.

Usage:
    python3 scripts/plot_quality_histogram.py case_dir [-o out.png]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--n-bins", type=int, default=30)
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[ERR] matplotlib not installed", file=sys.stderr)
        return 1

    import numpy as np
    import json

    case = args.case_dir
    qs: list[float] = []
    quality_json = case / "_work" / "native_bl_quality.json"
    if quality_json.exists():
        try:
            data = json.loads(quality_json.read_text())
            for k in ("quality", "qualities", "tet_quality"):
                if k in data and isinstance(data[k], list):
                    qs = [float(x) for x in data[k]]
                    break
        except Exception:
            pass

    npy_file = case / "_work" / "quality.npy"
    if not qs and npy_file.exists():
        try:
            qs = np.load(npy_file).tolist()
        except Exception:
            pass

    if not qs:
        print(f"[ERR] no quality data in {case}", file=sys.stderr)
        return 2

    qs_arr = np.asarray(qs, dtype=np.float64)
    out_path = args.output
    if out_path is None:
        out_path = case / "quality_histogram.png"

    fig, ax = plt.subplots(figsize=(10, 6))
    # color by quality range (grade A/B/C/D/F).
    colors = ["#d62728"] * args.n_bins  # red default.
    edges = np.linspace(0.0, 1.0, args.n_bins + 1)
    for i, lo in enumerate(edges[:-1]):
        if lo >= 0.6:
            colors[i] = "#2ca02c"  # green (A/B).
        elif lo >= 0.3:
            colors[i] = "#ff7f0e"  # orange (C).
        elif lo >= 0.1:
            colors[i] = "#bcbd22"  # yellow (D).
        else:
            colors[i] = "#d62728"  # red (F).

    counts, _ = np.histogram(qs_arr, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    ax.bar(centers, counts, width=edges[1] - edges[0],
           color=colors, edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Quality (Klingner mean-ratio)")
    ax.set_ylabel("Cell count")
    ax.set_title(
        f"Quality histogram — n={len(qs)}, "
        f"min={qs_arr.min():.3f}, mean={qs_arr.mean():.3f}, max={qs_arr.max():.3f}"
    )
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig(str(out_path), dpi=120)
    plt.close(fig)
    print(f"[OK] saved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
