"""native_tet hard-geometry matrix bench (roadmap A-2).

Measurement-only. First full sweep of the *self-implemented* native_tet engine
(AUTO_TESSELL_P4C_PYTETWILD=0, i.e. the pytetwild fallback disabled) across the
watertight single-body STL fixtures in tests/benchmarks/, to find where it stops
working on general geometry beyond cube/cylinder.

Protocol per shape: draft / tier_hint="native_tet" / N=2000 / P4C disabled,
mirroring scripts/smoke_native_cylinder.py.

Two solid-fidelity ratios are reported together (total boundary area alone was a
trap in the cube campaign):
  * area-ratio = Σ|boundary face area| / input STL surface area
  * vol-ratio  = Σ|cell volume|       / input STL closed volume (divergence thm)
Degenerate cells are counted vertex-first (|det|/6 < 1e-9), independent of face
orientation. checkMesh skew / non-ortho / verdict / wall-clock are also captured.

Each shape is meshed in its own subprocess with a 120 s timeout so a hang on one
hard geometry does not sink the sweep.

Usage:
    python scripts/bench_native_tet_matrix.py            # run the whole matrix
    python scripts/bench_native_tet_matrix.py --stl PATH # worker: mesh one shape
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEGEN_TOL = 1e-9
TIMEOUT_S = 120

# Watertight single-body STL fixtures. Chosen by ls of tests/benchmarks/ with the
# intentional-bad (broken_*, *_open, degenerate_*, mixed_*, self_intersecting_*,
# nonmanifold_*, highly_skewed_*), multi-body (two_spheres, *disconnected*),
# non-STL (*.step) and large/medium (large_mesh_250k, sphere_20k) inputs excluded.
INCLUDE = [
    "cube.stl",
    "cylinder.stl",
    "sphere.stl",
    "sphere_watertight.stl",
    "naca0012.stl",
    "trimesh_box.stl",
    "external_flow_isolated_box.stl",
    "very_thin_disk_0_01mm.stl",
    "extreme_aspect_ratio_needle.stl",
    "high_genus_dual_torus.stl",
    "multi_scale_sphere_with_micro_spikes.stl",
    "many_small_features_perforated_plate.stl",
    "sharp_features_micro_ridge.stl",
]

EXCLUDED_NOTE = {
    "broken_sphere.stl": "intentional-bad (broken)",
    "degenerate_faces_sliver_triangles.stl": "intentional-bad (degenerate)",
    "hemisphere_open.stl": "open surface",
    "hemisphere_open_partial.stl": "open surface",
    "highly_skewed_mesh_flat_triangles.stl": "intentional-bad (skewed/flat)",
    "mixed_features_wing_with_spike.stl": "mixed_* (intentional)",
    "mixed_watertight_and_open.stl": "mixed_* (intentional)",
    "nonmanifold_disconnected.stl": "non-manifold / disconnected",
    "self_intersecting_crossed_planes.stl": "self-intersecting (intentional)",
    "coarse_to_fine_gradation_two_spheres.stl": "multi-body (2 spheres)",
    "five_disconnected_spheres.stl": "multi-body (5 spheres)",
    "trimesh_duct.stl": "open tube (uncertain watertight)",
    "large_mesh_250k_faces.stl": "large (excluded 1st pass)",
    "sphere_20k.stl": "medium/redundant with sphere.stl",
    "*.step": "non-STL",
}


# --------------------------------------------------------------------------- #
# Worker: mesh ONE stl, print a JSON metrics line.
# --------------------------------------------------------------------------- #
def _worker(stl_path: Path) -> dict:
    os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    sys.path.insert(0, str(REPO))

    import numpy as np
    import trimesh

    from core.utils.logging import configure_logging

    configure_logging(verbose=False, json=True)

    from core.pipeline.orchestrator import PipelineOrchestrator
    from core.utils.polymesh_reader import (
        parse_foam_faces,
        parse_foam_labels,
        parse_foam_points,
    )

    out: dict = {"stl": stl_path.name}

    # ---- input STL solid metrics (trimesh + divergence theorem) ----
    tm = trimesh.load(str(stl_path), force="mesh")
    out["stl_area"] = float(tm.area)
    out["stl_volume"] = float(abs(tm.volume))
    out["stl_watertight"] = bool(tm.is_watertight)
    try:
        out["stl_bodies"] = int(tm.body_count)
    except Exception:
        out["stl_bodies"] = -1

    with tempfile.TemporaryDirectory() as t:
        case = Path(t) / "case"
        t0 = time.monotonic()
        try:
            res = PipelineOrchestrator().run(
                stl_path, case, quality_level="draft", mesh_type="tet",
                tier_hint="native_tet", max_iterations=1, auto_retry="off",
                write_of_case=True, max_cells=2000,
                tier_specific_params={"max_cells": 2000, "target_cells": 2000},
            )
        except Exception as e:  # noqa: BLE001
            out["time_s"] = round(time.monotonic() - t0, 1)
            out["polymesh"] = False
            out["error"] = f"{type(e).__name__}: {e}"[:200]
            return out
        out["time_s"] = round(time.monotonic() - t0, 1)

        poly = case / "constant" / "polyMesh"
        if not (poly / "points").exists():
            out["polymesh"] = False
            out["error"] = (str(res.error) if getattr(res, "error", None)
                            else "no polyMesh")[:200]
            return out
        out["polymesh"] = True

        pts = np.asarray(parse_foam_points(poly / "points"), float)
        faces = [list(int(v) for v in f) for f in parse_foam_faces(poly / "faces")]
        owner = np.asarray(parse_foam_labels(poly / "owner"), np.int64)
        nb = np.asarray(parse_foam_labels(poly / "neighbour"), np.int64)
        n_int = len(nb)
        n_faces = len(faces)

        # ---- boundary area ----
        def area_vec(vs: list[int]) -> np.ndarray:
            p = pts[vs]
            a = np.zeros(3)
            for i in range(len(p)):
                a += np.cross(p[i], p[(i + 1) % len(p)])
            return 0.5 * a

        bnd_area = 0.0
        for f in range(n_int, n_faces):
            bnd_area += float(np.linalg.norm(area_vec(faces[f])))
        out["bnd_area"] = bnd_area
        out["area_ratio"] = (bnd_area / out["stl_area"]
                             if out["stl_area"] > 0 else 0.0)

        # ---- per-cell reconstruction (cell -> unique vertex set) ----
        n_cells = 1 + int(max(owner.max() if len(owner) else -1,
                              nb.max() if len(nb) else -1))
        cell_pts: list[set[int]] = [set() for _ in range(n_cells)]
        for f in range(n_faces):
            cell_pts[owner[f]].update(faces[f])
        for f in range(n_int):
            cell_pts[nb[f]].update(faces[f])

        # signed face-divergence volume, kept only as a fallback for any
        # non-tet cell (vertex-det below is the primary, orientation-free path).
        fdiv = np.zeros(n_cells)
        for f in range(n_faces):
            vs = faces[f]
            a = area_vec(vs)
            c = pts[vs].mean(axis=0)
            contrib = float(np.dot(c, a)) / 3.0
            fdiv[owner[f]] += contrib
            if f < n_int:
                fdiv[nb[f]] -= contrib

        # volume + degeneracy: vertex-based |det|/6, face-orientation
        # independent. native_tet is all-tet, so almost every cell has 4 verts.
        sum_abs_vol = 0.0
        degen = 0
        non_tet = 0
        for c in range(n_cells):
            vs = sorted(cell_pts[c])
            if len(vs) == 4:
                p = pts[vs]
                vol = abs(np.dot(p[1] - p[0],
                                 np.cross(p[2] - p[0], p[3] - p[0]))) / 6.0
                sum_abs_vol += vol
                if vol < DEGEN_TOL:
                    degen += 1
            else:
                non_tet += 1
                sum_abs_vol += abs(fdiv[c])
        out["cells"] = n_cells
        out["sum_abs_vol"] = float(sum_abs_vol)
        out["vol_ratio"] = (sum_abs_vol / out["stl_volume"]
                            if out["stl_volume"] > 0 else 0.0)
        out["degen_cells"] = degen
        out["non_tet_cells"] = non_tet

        # ---- evaluator summary ----
        qr = res.quality_report
        if qr is not None:
            cm = qr.evaluation_summary.checkmesh
            out["neg_vol_cells"] = int(cm.negative_volumes)
            out["max_skewness"] = float(cm.max_skewness)
            out["max_non_ortho"] = float(cm.max_non_orthogonality)
            out["verdict"] = str(qr.evaluation_summary.verdict.value)
        else:
            out["neg_vol_cells"] = None
            out["max_skewness"] = None
            out["max_non_ortho"] = None
            out["verdict"] = "?"
    return out


# --------------------------------------------------------------------------- #
# Driver: spawn one subprocess per shape, collect, tabulate.
# --------------------------------------------------------------------------- #
def _run_one(stl_path: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--stl", str(stl_path)],
            capture_output=True, text=True, timeout=TIMEOUT_S, env=env,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"stl": stl_path.name, "polymesh": False,
                "error": "TIMEOUT", "time_s": round(time.monotonic() - t0, 1),
                "verdict": "TIMEOUT"}
    # last JSON line on stdout is the metrics record.
    rec = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                rec = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if rec is None:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        return {"stl": stl_path.name, "polymesh": False,
                "error": "no metrics (" + " | ".join(tail) + ")"[:180],
                "time_s": round(time.monotonic() - t0, 1), "verdict": "ERR"}
    return rec


def _fmt(v, spec: str) -> str:
    if v is None:
        return "-"
    try:
        return format(v, spec)
    except (ValueError, TypeError):
        return str(v)


def _driver() -> None:
    bench = REPO / "tests" / "benchmarks"
    shapes = [bench / n for n in INCLUDE if (bench / n).exists()]
    missing = [n for n in INCLUDE if not (bench / n).exists()]

    records = []
    for sp in shapes:
        print(f"[bench] {sp.name} ...", flush=True)
        rec = _run_one(sp)
        records.append(rec)
        print(f"    -> verdict={rec.get('verdict')} cells={rec.get('cells')} "
              f"degen={rec.get('degen_cells')} time={rec.get('time_s')}s",
              flush=True)

    # ---- markdown table ----
    lines = []
    lines.append("# native_tet hard-geometry matrix (P4C=0, draft, N=2000)\n")
    lines.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M')} — "
                 "engine: self-implemented native_tet, pytetwild fallback OFF._\n")
    lines.append("Protocol per shape: draft / tier_hint=native_tet / N=2000 / "
                 "P4C disabled / 120s timeout, subprocess-isolated.\n")
    lines.append("- **area-ratio** = Σ|boundary face area| / STL surface area "
                 "(≈1 = boundary tracks the surface)")
    lines.append("- **vol-ratio** = Σ|cell volume| / STL closed volume "
                 "(≈1 = solid fills the body, no over/under-fill)")
    lines.append("- **degen** = cells with |det|/6 < 1e-9 (vertex-based, "
                 "face-orientation independent)")
    lines.append("- **neg** = negative signed-volume cells; **nonTet** = "
                 "cells whose vertex set != 4\n")
    hdr = ("| shape | wt/bodies | cells | area-ratio | vol-ratio | degen | "
           "neg | nonTet | skew | nonOrtho | verdict | time |")
    sep = ("|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines.append(hdr)
    lines.append(sep)
    for r in records:
        wt = ("Y" if r.get("stl_watertight") else "N") + "/" + str(r.get("stl_bodies", "-"))
        if not r.get("polymesh"):
            lines.append(
                f"| {r['stl']} | {wt} | — | — | — | — | — | — | — | — | "
                f"**{r.get('verdict','FAIL')}** ({r.get('error','?')[:40]}) | "
                f"{_fmt(r.get('time_s'), '.0f')}s |")
            continue
        lines.append(
            f"| {r['stl']} | {wt} | {r.get('cells')} | "
            f"{_fmt(r.get('area_ratio'), '.3f')} | {_fmt(r.get('vol_ratio'), '.3f')} | "
            f"{r.get('degen_cells')} | {r.get('neg_vol_cells')} | "
            f"{r.get('non_tet_cells')} | {_fmt(r.get('max_skewness'), '.2f')} | "
            f"{_fmt(r.get('max_non_ortho'), '.1f')} | {r.get('verdict')} | "
            f"{_fmt(r.get('time_s'), '.0f')}s |")

    lines.append("\n## Excluded inputs (1st pass)\n")
    for name, why in EXCLUDED_NOTE.items():
        lines.append(f"- `{name}` — {why}")
    if missing:
        lines.append(f"\n_Missing from INCLUDE (not found): {missing}_")

    out_md = REPO / "harness" / "bench_native_tet_matrix.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[bench] wrote {out_md}")

    # also dump raw json next to it for downstream harness use.
    (out_md.with_suffix(".json")).write_text(
        json.dumps(records, indent=2), encoding="utf-8")

    # ---- console summary ----
    npass = sum(1 for r in records
                if r.get("polymesh") and str(r.get("verdict", "")).upper()
                in ("PASS", "PASS_WITH_WARNINGS", "SOFT_PASS"))
    print(f"[bench] PASS-ish: {npass}/{len(records)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", type=str, default=None)
    args = ap.parse_args()
    if args.stl:
        rec = _worker(Path(args.stl))
        print(json.dumps(rec), flush=True)
    else:
        _driver()


if __name__ == "__main__":
    main()
