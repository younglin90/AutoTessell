#!/usr/bin/env python3
"""Classify bench failures by failure mode.

Reads the bench RUN_ROOT, runs ``NativeMeshChecker`` on each
case, and for failing STLs auto-classifies them by inspecting
the top-K worst internal faces:

- ``sliver_tri``  — top faces have edge-length aspect > 10x
- ``pancake``     — top faces have small cell_dist / face_size
- ``extreme_skew``— max_skewness > 8
- ``other``       — none of the above

Useful for triaging which fix to prioritise (e.g. "sliver_tri"
cases need sliver-removal in the tet mesher; "pancake" cases
need BL-bulk transition smoothing).

Usage::

    python3 tests/stl/bench_cavity_eval_classify.py
    AUTO_TESSELL_BENCH_CAVITY_QUALITY=draft \\
        python3 tests/stl/bench_cavity_eval_classify.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from core.evaluator.native_checker import NativeMeshChecker
from core.evaluator.report import get_thresholds
from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels


RUN_ROOT = Path(
    os.environ.get(
        "AUTO_TESSELL_BENCH_CAVITY_RUN_ROOT",
        "/tmp/autotessell_bench_cavity_eval",
    )
)
QUALITY = os.environ.get("AUTO_TESSELL_BENCH_CAVITY_QUALITY", "fine")


def _classify(case: Path, max_skew: float) -> tuple[str, dict]:
    if max_skew > 8.0:
        return "extreme_skew", {"max_skew": round(max_skew, 2)}
    poly = case / "constant" / "polyMesh"
    pts_text = (poly / "points").read_text()
    m = re.search(r"\n(\d+)\n\(", pts_text)
    n_pts = int(m.group(1)) if m else 0
    body = pts_text[pts_text.index("(") :]
    nums = re.findall(r"-?[\d.eE+-]+", body)
    pts = np.array(nums, dtype=np.float64).reshape(-1, 3)[:n_pts]
    faces = parse_foam_faces(poly / "faces")
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    nbr = np.asarray(parse_foam_labels(poly / "neighbour"), dtype=np.int64)
    n_cells = max(int(owner.max()),
                  int(nbr.max()) if nbr.size else 0) + 1
    cc = np.zeros((n_cells, 3))
    cnt = np.zeros(n_cells)
    for fi, f in enumerate(faces):
        fc = pts[list(f)].mean(axis=0)
        cc[owner[fi]] += fc
        cnt[owner[fi]] += 1
        if fi < len(nbr):
            cc[nbr[fi]] += fc
            cnt[nbr[fi]] += 1
    cc /= np.maximum(cnt, 1)[:, None]

    rows = []
    for fi in range(len(nbr)):
        f = faces[fi]
        p = pts[list(f)]
        n = np.zeros(3)
        for k in range(len(f)):
            n += np.cross(p[k], p[(k + 1) % len(f)])
        nn = float(np.linalg.norm(n))
        if nn < 1e-30:
            continue
        n /= nn
        d = cc[nbr[fi]] - cc[owner[fi]]
        dn = float(np.linalg.norm(d))
        if dn < 1e-30:
            continue
        cos_t = float(min(1.0, max(0.0, abs(np.dot(n, d)) / dn)))
        a_deg = float(np.degrees(np.arccos(cos_t)))
        if a_deg > 80.0:
            edges = [
                float(np.linalg.norm(p[j] - p[(j + 1) % len(f)]))
                for j in range(len(f))
            ]
            face_max = max(edges)
            face_min = min(edges)
            face_size = face_max
            edge_aspect = face_max / max(face_min, 1e-30)
            rows.append((
                a_deg, dn, face_size, edge_aspect,
            ))
    if not rows:
        return "other", {}
    rows.sort(reverse=True)
    top = rows[: min(10, len(rows))]
    avg_aspect = float(np.mean([r[3] for r in top]))
    avg_ratio = float(np.mean([r[1] / r[2] for r in top]))
    if avg_aspect > 10.0:
        return "sliver_tri", {
            "avg_edge_aspect_top10": round(avg_aspect, 1),
            "n_above_80": len(rows),
        }
    if avg_ratio < 0.7:
        return "pancake", {
            "avg_cell_dist_over_face_top10": round(avg_ratio, 2),
            "n_above_80": len(rows),
        }
    return "other", {
        "avg_edge_aspect_top10": round(avg_aspect, 1),
        "avg_cell_dist_over_face_top10": round(avg_ratio, 2),
        "n_above_80": len(rows),
    }


def main() -> int:
    thresholds = get_thresholds(QUALITY)
    hard_no = float(thresholds.get("hard_non_ortho", 65.0))
    hard_skew = float(thresholds.get("hard_skewness", 4.0))
    cases = sorted(p for p in RUN_ROOT.iterdir() if p.is_dir())
    print(f"quality={QUALITY}  hard_no={hard_no}  hard_skew={hard_skew}")
    print(f"{'case':<20}\tverdict\tmax_no\tmax_skew\tcategory\tdetails")
    for case in cases:
        if not (case / "constant" / "polyMesh" / "owner").exists():
            continue
        try:
            r = NativeMeshChecker().run(case)
        except Exception:  # noqa: BLE001
            continue
        max_no = float(r.max_non_orthogonality)
        max_skew = float(r.max_skewness)
        min_det = float(r.min_determinant)
        hard_fail = (
            max_no > hard_no
            or max_skew > hard_skew
            or min_det <= 0.0
            or int(getattr(r, "negative_volumes", 0)) > 0
        )
        verdict = "FAIL" if hard_fail else "PASS"
        if hard_fail:
            cat, details = _classify(case, max_skew)
        else:
            cat, details = "pass", {}
        print(
            f"{case.name:<20}\t{verdict}\t{round(max_no, 1)}\t"
            f"{round(max_skew, 2)}\t{cat}\t{details}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
