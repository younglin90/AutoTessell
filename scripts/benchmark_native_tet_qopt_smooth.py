#!/usr/bin/env python3
"""Deterministic benchmark for QOPT guarded interior smoothing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_structured_tet_mesh(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build an n^3 vertex grid split into deterministic tetrahedra."""
    if n < 3:
        raise ValueError("grid size must be >= 3")
    coords = np.linspace(0.0, 1.0, n)
    points = np.array(
        [[x, y, z] for z in coords for y in coords for x in coords],
        dtype=np.float64,
    )

    def vid(i: int, j: int, k: int) -> int:
        return k * n * n + j * n + i

    tets: list[list[int]] = []
    for k in range(n - 1):
        for j in range(n - 1):
            for i in range(n - 1):
                v000 = vid(i, j, k)
                v100 = vid(i + 1, j, k)
                v010 = vid(i, j + 1, k)
                v110 = vid(i + 1, j + 1, k)
                v001 = vid(i, j, k + 1)
                v101 = vid(i + 1, j, k + 1)
                v011 = vid(i, j + 1, k + 1)
                v111 = vid(i + 1, j + 1, k + 1)
                tets.extend(
                    [
                        [v000, v100, v010, v001],
                        [v100, v110, v010, v111],
                        [v100, v010, v001, v111],
                        [v100, v001, v101, v111],
                        [v010, v001, v011, v111],
                        [v100, v010, v111, v001],
                    ]
                )
    tets_array = np.asarray(tets, dtype=np.int64)
    v = points[tets_array]
    vol6 = np.einsum(
        "ij,ij->i",
        v[:, 1] - v[:, 0],
        np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 0]),
    )
    flip = vol6 < 0.0
    tets_array[flip, 2], tets_array[flip, 3] = (
        tets_array[flip, 3].copy(),
        tets_array[flip, 2].copy(),
    )
    boundary = np.array(
        [
            vid(i, j, k)
            for k in range(n)
            for j in range(n)
            for i in range(n)
            if i in {0, n - 1} or j in {0, n - 1} or k in {0, n - 1}
        ],
        dtype=np.int64,
    )
    return points, tets_array, boundary


def perturb_interior(points: np.ndarray, n: int, amplitude: float) -> np.ndarray:
    out = points.copy()
    for index, point in enumerate(out):
        i = index % n
        j = (index // n) % n
        k = index // (n * n)
        if i in {0, n - 1} or j in {0, n - 1} or k in {0, n - 1}:
            continue
        phase = np.array(
            [
                np.sin(17.0 * point[1] + 3.0 * point[2]),
                np.cos(13.0 * point[0] + 5.0 * point[2]),
                np.sin(11.0 * point[0] + 7.0 * point[1]),
            ],
            dtype=np.float64,
        )
        out[index] = point + amplitude * phase / float(n - 1)
    return out


def quality_stats(points: np.ndarray, tets: np.ndarray) -> dict[str, float]:
    from core.generator.native_tet.quality import tet_shape_quality

    q = tet_shape_quality(points, tets)
    if q.size == 0:
        return {"min_q": 0.0, "mean_q": 0.0}
    return {"min_q": float(q.min()), "mean_q": float(q.mean())}


def run_once(
    points: np.ndarray,
    tets: np.ndarray,
    locked: np.ndarray,
    *,
    guarded: bool,
    n_iter: int,
    relax: float,
) -> dict[str, Any]:
    from core.generator.native_tet.smooth import smooth_interior

    trial = points.copy()
    pre = quality_stats(trial, tets)
    started = time.perf_counter()
    result = smooth_interior(
        trial,
        tets,
        locked_vertex_ids=locked,
        n_iter=n_iter,
        relax=relax,
        quality_guard=guarded,
    )
    elapsed = time.perf_counter() - started
    post = quality_stats(trial, tets)
    return {
        "guarded": bool(guarded),
        "elapsed_s": float(elapsed),
        "moved": int(result.n_interior_moved),
        "max_displacement": float(result.max_displacement),
        "qopt_attempted": int(result.qopt_attempted),
        "qopt_accepted": int(result.qopt_accepted),
        "qopt_rejected_volume": int(result.qopt_rejected_volume),
        "qopt_rejected_quality": int(result.qopt_rejected_quality),
        "pre": pre,
        "post": post,
    }


def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    points, tets, locked = build_structured_tet_mesh(int(args.grid))
    points = perturb_interior(points, int(args.grid), float(args.perturb))
    rows = []
    for _ in range(int(args.repeat)):
        rows.append(
            run_once(
                points, tets, locked,
                guarded=False, n_iter=int(args.iters), relax=float(args.relax),
            )
        )
        rows.append(
            run_once(
                points, tets, locked,
                guarded=True, n_iter=int(args.iters), relax=float(args.relax),
            )
        )
    summary = {
        "grid": int(args.grid),
        "points": int(points.shape[0]),
        "tets": int(tets.shape[0]),
        "locked": int(locked.size),
        "iters": int(args.iters),
        "relax": float(args.relax),
        "repeat": int(args.repeat),
        "rows": rows,
    }
    for guarded in (False, True):
        selected = [row for row in rows if row["guarded"] is guarded]
        summary[f"{'guarded' if guarded else 'unguarded'}_mean_elapsed_s"] = float(
            np.mean([row["elapsed_s"] for row in selected])
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=int, default=9)
    parser.add_argument("--iters", type=int, default=2)
    parser.add_argument("--relax", type=float, default=0.35)
    parser.add_argument("--perturb", type=float, default=0.15)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = benchmark(args)
    text = json.dumps(result, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
