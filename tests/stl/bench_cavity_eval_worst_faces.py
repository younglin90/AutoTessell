#!/usr/bin/env python3
"""Locate the worst-non-orthogonality faces in a polyMesh.

Companion diagnostic for bench_cavity_eval.py.  Given a case
directory, computes per-internal-face non-orthogonality angles
and prints the top-K worst faces with their owner/neighbour cell
centroids and vertex coordinates so the bad cells can be located
visually.

Usage::

    python3 tests/stl/bench_cavity_eval_worst_faces.py CASE_DIR
    python3 tests/stl/bench_cavity_eval_worst_faces.py CASE_DIR --top 10
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


def _read_points(points_path: Path) -> np.ndarray:
    text = points_path.read_text()
    m = re.search(r"\n(\d+)\n\(", text)
    n_pts = int(m.group(1)) if m else 0
    body = text[text.index("(") :]
    nums = re.findall(r"-?[\d.eE+-]+", body)
    arr = np.array(nums, dtype=np.float64).reshape(-1, 3)[:n_pts]
    return arr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path)
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()
    poly = args.case / "constant" / "polyMesh"
    if not poly.is_dir():
        print(f"polyMesh missing under {args.case}", file=sys.stderr)
        return 1

    pts = _read_points(poly / "points")
    faces = parse_foam_faces(poly / "faces")
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(
        parse_foam_labels(poly / "neighbour"), dtype=np.int64,
    )
    n_cells = max(int(owner.max()),
                  int(neighbour.max()) if neighbour.size else 0) + 1

    cc = np.zeros((n_cells, 3))
    cnt = np.zeros(n_cells)
    for fi, f in enumerate(faces):
        fc = pts[list(f)].mean(axis=0)
        cc[owner[fi]] += fc
        cnt[owner[fi]] += 1
        if fi < len(neighbour):
            cc[neighbour[fi]] += fc
            cnt[neighbour[fi]] += 1
    cnt = np.maximum(cnt, 1)
    cc /= cnt[:, None]

    rows: list[tuple[float, int]] = []
    hist: Counter[str] = Counter()
    for fi in range(len(neighbour)):
        f = faces[fi]
        p = pts[list(f)]
        n = np.zeros(3)
        for k in range(len(f)):
            a = p[k]
            b = p[(k + 1) % len(f)]
            n += np.cross(a, b)
        nn = float(np.linalg.norm(n))
        if nn < 1e-30:
            continue
        n /= nn
        d = cc[neighbour[fi]] - cc[owner[fi]]
        dn = float(np.linalg.norm(d))
        if dn < 1e-30:
            continue
        cos_t = float(abs(np.dot(n, d)) / dn)
        cos_t = min(1.0, max(0.0, cos_t))
        a_deg = float(np.degrees(np.arccos(cos_t)))
        rows.append((a_deg, fi))
        if a_deg > 80:
            hist[">80"] += 1
        elif a_deg > 70:
            hist["70-80"] += 1
        elif a_deg > 60:
            hist["60-70"] += 1
        else:
            hist["<=60"] += 1
    rows.sort(reverse=True)
    print(f"case: {args.case}")
    print(f"n_internal_faces: {len(neighbour)}")
    print(f"non-ortho histogram: {dict(hist)}")
    print()
    print(f"Top {args.top} worst faces:")
    for k, (angle, fi) in enumerate(rows[: args.top]):
        f = faces[fi]
        owner_cid = int(owner[fi])
        nb_cid = int(neighbour[fi])
        edges = []
        for j in range(len(f)):
            edges.append(
                float(np.linalg.norm(pts[f[j]] - pts[f[(j + 1) % len(f)]]))
            )
        d_cells = float(np.linalg.norm(cc[nb_cid] - cc[owner_cid]))
        print(
            f"  [{k + 1}] face_id={fi} angle={round(angle, 2)}° "
            f"owner={owner_cid} neighbour={nb_cid}"
        )
        print(
            f"        n_verts={len(f)} edge_len min={round(min(edges), 4)} "
            f"max={round(max(edges), 4)} cell_dist={round(d_cells, 4)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
