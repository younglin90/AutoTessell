#!/usr/bin/env python3
"""Native tet replacement regression harness.

Builds a 100+ local-case manifest from existing benchmark STL/STEP files plus
deterministic STL variants, then runs the public CLI through the strict
``native_tet`` tier and records one JSON row per case.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path("/tmp/autotessell_native_tet_replacement_matrix")


def _source_files() -> list[Path]:
    roots = [ROOT / "tests" / "benchmarks", ROOT / "tests" / "stl"]
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".stl", ".step", ".stp"}:
                continue
            parts = set(path.parts)
            if "_work" in parts or "constant" in parts or path.name == "preprocessed.stl":
                continue
            real = path.resolve()
            if real not in seen:
                seen.add(real)
                out.append(path)
    return sorted(out, key=lambda p: str(p.relative_to(ROOT)))


def _variant_name(path: Path, variant: str) -> str:
    stem = str(path.relative_to(ROOT)).replace("/", "__").replace("\\", "__")
    return f"{stem}__{variant}.stl"


def _write_stl_variants(sources: list[Path], out_dir: Path, max_variants: int) -> list[Path]:
    try:
        import numpy as np
        import trimesh
    except Exception:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    variants: list[Path] = []
    transforms = [
        (
            "scale_aniso",
            np.array(
                [[1.35, 0.00, 0.00, 0.0],
                 [0.00, 0.72, 0.00, 0.0],
                 [0.00, 0.00, 1.10, 0.0],
                 [0.00, 0.00, 0.00, 1.0]],
                dtype=float,
            ),
        ),
        (
            "shear_xy",
            np.array(
                [[1.00, 0.18, 0.00, 0.0],
                 [0.00, 1.00, 0.07, 0.0],
                 [0.00, 0.00, 1.00, 0.0],
                 [0.00, 0.00, 0.00, 1.0]],
                dtype=float,
            ),
        ),
        (
            "rotate_scale",
            np.array(
                [[0.866, -0.500, 0.000, 0.0],
                 [0.500, 0.866, 0.000, 0.0],
                 [0.000, 0.000, 0.830, 0.0],
                 [0.000, 0.000, 0.000, 1.0]],
                dtype=float,
            ),
        ),
    ]
    for source in sources:
        if len(variants) >= max_variants:
            break
        if source.suffix.lower() != ".stl":
            continue
        try:
            mesh = trimesh.load(str(source), force="mesh")
            if getattr(mesh, "faces", []).shape[0] <= 0:
                continue
            if int(mesh.faces.shape[0]) > 50_000:
                continue
            for variant, matrix in transforms:
                if len(variants) >= max_variants:
                    break
                copy = mesh.copy()
                copy.apply_transform(matrix)
                target = out_dir / _variant_name(source, variant)
                copy.export(str(target))
                variants.append(target)
        except Exception:
            continue
    return variants


def build_manifest(run_root: Path, target_cases: int) -> list[Path]:
    sources = _source_files()
    if len(sources) >= target_cases:
        return sources[:target_cases]
    variants = _write_stl_variants(
        [p for p in sources if p.suffix.lower() == ".stl"],
        run_root / "generated_inputs",
        max(0, target_cases - len(sources)),
    )
    return sources + variants


def _case_name(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = path
    return str(rel).replace("/", "__").replace("\\", "__").replace(":", "_")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _flatten_report(case_dir: Path) -> dict[str, Any]:
    qr = _read_json(case_dir / "quality_report.json")
    summary = qr.get("evaluation_summary") or {}
    cm = summary.get("checkmesh") or {}
    fidelity = summary.get("geometry_fidelity") or {}
    phase2 = (summary.get("additional_metrics") or {}).get("native_bl_phase2") or {}
    glog = _read_json(case_dir / "generator_log.json")
    exec_summary = glog.get("execution_summary") or {}
    cdt_plateau = _read_json(case_dir / "_work" / "native_tet_cdt_plateau.json")
    if not cdt_plateau:
        cdt_plateau = _read_json(case_dir / "_work" / "native_tet_cdt_post_run.json")
    if not cdt_plateau:
        cdt_plateau = _post_run_cdt_diagnostics(case_dir)
    return {
        "verdict": summary.get("verdict"),
        "tier": summary.get("tier_evaluated") or exec_summary.get("selected_tier"),
        "cells": cm.get("cells"),
        "points": cm.get("points"),
        "negative_volumes": cm.get("negative_volumes"),
        "max_non_ortho": cm.get("max_non_orthogonality"),
        "max_boundary_skewness": cm.get("max_boundary_skewness"),
        "max_internal_skewness": cm.get("max_internal_skewness"),
        "max_skewness": cm.get("max_skewness"),
        "max_aspect_ratio": cm.get("max_aspect_ratio"),
        "min_face_weight": cm.get("min_face_weight"),
        "min_vol_ratio": cm.get("min_vol_ratio"),
        "min_determinant": cm.get("min_determinant"),
        "hausdorff_relative": fidelity.get("hausdorff_relative"),
        "n_self_intersect_pre": fidelity.get("n_self_intersect_pre"),
        "bl_prisms": phase2.get("n_prism_cells"),
        "bl_requested_layers": phase2.get("requested_layers"),
        "bl_used_layers": phase2.get("used_layers") or phase2.get("lcr_min_layers_used"),
        "bl_degenerate_prisms": phase2.get("n_degenerate_prisms"),
        "generator_time_s": exec_summary.get("total_time_seconds"),
        "cdt_missing": cdt_plateau.get("missing"),
        "cdt_invalid": cdt_plateau.get("invalid"),
        "cdt_duplicate": cdt_plateau.get("duplicate"),
        "cdt_no_cavity": cdt_plateau.get("no_cavity"),
        "cdt_cavity_too_large": cdt_plateau.get("cavity_too_large"),
        "cdt_protected_encroachment": cdt_plateau.get("protected_encroachment"),
        "cdt_empty_boundary": cdt_plateau.get("empty_boundary"),
        "cdt_ready": cdt_plateau.get("ready"),
        "cdt_mode": cdt_plateau.get("mode"),
        "cdt_error": cdt_plateau.get("error"),
    }


def _post_run_cdt_diagnostics(case_dir: Path) -> dict[str, Any]:
    """Best-effort CDT blocker diagnostic from written tet polyMesh."""
    try:
        import numpy as np
        import trimesh
        from core.evaluator.native_checker import (
            parse_foam_faces,
            parse_foam_labels_array,
            parse_foam_points_array,
        )
        from core.generator.native_tet.cdt_recovery import (
            diagnose_cdt_recovery_blockers,
        )

        poly_dir = case_dir / "constant" / "polyMesh"
        surface_path = case_dir / "_work" / "preprocessed.stl"
        if not poly_dir.is_dir() or not surface_path.exists():
            return {}
        points = parse_foam_points_array(poly_dir / "points")
        faces = parse_foam_faces(poly_dir / "faces")
        owner = parse_foam_labels_array(poly_dir / "owner")
        neighbour = parse_foam_labels_array(poly_dir / "neighbour")
        if points.size == 0 or not faces or owner.size == 0:
            return {}

        max_cell = int(owner.max(initial=-1))
        if neighbour.size:
            valid_neighbour = neighbour[neighbour >= 0]
            max_cell = max(max_cell, int(valid_neighbour.max(initial=-1)))
        cell_faces: list[list[int]] = [[] for _ in range(max_cell + 1)]
        for face_id, cell_id in enumerate(owner):
            if 0 <= int(cell_id) <= max_cell:
                cell_faces[int(cell_id)].append(face_id)
        for face_id, cell_id in enumerate(neighbour):
            if 0 <= int(cell_id) <= max_cell:
                cell_faces[int(cell_id)].append(face_id)

        tets: list[list[int]] = []
        for face_ids in cell_faces:
            verts: set[int] = set()
            for face_id in face_ids:
                if 0 <= int(face_id) < len(faces):
                    verts.update(int(v) for v in faces[int(face_id)])
            if len(verts) == 4:
                tets.append(sorted(verts))
        if not tets:
            return {}

        surface = trimesh.load(str(surface_path), force="mesh")
        V_surf = np.asarray(surface.vertices, dtype=np.float64)
        F_surf = np.asarray(surface.faces, dtype=np.int64)
        diag = diagnose_cdt_recovery_blockers(
            points,
            np.asarray(tets, dtype=np.int64),
            V_surf,
            F_surf,
            max_edges=200,
        )
        out = {
            "missing": diag.n_missing_edges,
            "invalid": diag.n_invalid_edges,
            "duplicate": diag.n_duplicate_candidates,
            "no_cavity": diag.n_no_cavity,
            "cavity_too_large": diag.n_cavity_too_large,
            "protected_encroachment": diag.n_protected_edge_encroachment,
            "empty_boundary": diag.n_empty_boundary,
            "ready": diag.n_ready_for_insertion,
            "mode": "post_run_polymesh",
        }
        target = case_dir / "_work" / "native_tet_cdt_post_run.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160]}


def run_one(path: Path, run_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    case_dir = run_root / "cases" / _case_name(path)
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "1")
    env.setdefault("AUTO_TESSELL_P4C_TOTAL_TIMEOUT_S", str(args.p4c_timeout))
    if args.aggressive_repair:
        env["AUTO_TESSELL_AGGR_REPAIR"] = "1"
    if args.l3_repair:
        env["AUTO_TESSELL_L3_AI_REPAIR"] = "1"
        env.setdefault("AUTO_TESSELL_L3_VOXEL_RES", str(args.l3_voxel_res))
    cmd = [
        sys.executable,
        "-m",
        "cli.main",
        "run",
        str(path),
        "-o",
        str(case_dir),
        "--mesh-type",
        "tet",
        "--tier",
        "native_tet",
        "--strict-tier",
        "--quality",
        args.quality,
        "--checker-engine",
        "native",
        "--auto-retry",
        "off",
        "--max-cells",
        str(args.max_cells),
        "--bl-layers",
        str(args.bl_layers),
        "--tier-param",
        "post_layers_engine=auto",
        "--tier-param",
        f"post_layers_num_layers={args.bl_layers}",
        "--tier-param",
        f"target_cells={args.max_cells}",
        "--tier-param",
        f"max_cells={args.max_cells}",
        "--tier-param",
        "enable_cdt_recovery=true",
        "--tier-param",
        f"cdt_recovery_max_cycles={args.cdt_cycles}",
        "--tier-param",
        f"cdt_recovery_outer_iter={args.cdt_outer_iter}",
        "--tier-param",
        f"cdt_recovery_points_budget={args.cdt_points_budget}",
    ]
    started = time.monotonic()
    row: dict[str, Any] = {
        "source": str(path),
        "case_dir": str(case_dir),
        "quality": args.quality,
    }
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=float(args.timeout),
        )
        row["returncode"] = int(proc.returncode)
        row["elapsed_s"] = round(time.monotonic() - started, 3)
        row["log_tail"] = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        row.update(
            {
                "returncode": 124,
                "elapsed_s": round(time.monotonic() - started, 3),
                "timeout": True,
                "log_tail": "\n".join((stdout + stderr).splitlines()[-80:]) or str(exc)[:400],
            }
        )
    row.update(_flatten_report(case_dir))
    row["ok"] = bool(
        row.get("returncode") == 0
        and str(row.get("verdict")) in {"PASS", "PASS_WITH_WARNINGS"}
        and (row.get("cells") or 0) > 0
        and (row.get("negative_volumes") in {0, 0.0})
    )
    return row


def _write_rows(rows: list[dict[str, Any]], run_root: Path) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    json_path = run_root / "rows.json"
    csv_path = run_root / "rows.csv"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--target-cases", type=int, default=120)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quality", default="fine")
    parser.add_argument("--max-cells", type=int, default=2000)
    parser.add_argument("--bl-layers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--p4c-timeout", type=float, default=90.0)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--aggressive-repair", action="store_true")
    parser.add_argument("--l3-repair", action="store_true")
    parser.add_argument("--l3-voxel-res", type=int, default=48)
    parser.add_argument("--cdt-cycles", type=int, default=2)
    parser.add_argument("--cdt-outer-iter", type=int, default=1)
    parser.add_argument("--cdt-points-budget", type=int, default=80)
    args = parser.parse_args()

    manifest = [Path(item) for item in args.source] if args.source else build_manifest(args.run_root, args.target_cases)
    if args.limit > 0:
        manifest = manifest[: args.limit]
    args.run_root.mkdir(parents=True, exist_ok=True)
    (args.run_root / "manifest.txt").write_text(
        "\n".join(str(p) for p in manifest) + "\n",
        encoding="utf-8",
    )

    rows: list[dict[str, Any]] = []
    for index, path in enumerate(manifest, start=1):
        row = run_one(path, args.run_root, args)
        rows.append(row)
        _write_rows(rows, args.run_root)
        status = "OK" if row.get("ok") else "FAIL"
        print(
            f"{status} {index}/{len(manifest)} {path} "
            f"cells={row.get('cells')} no={row.get('max_non_ortho')} "
            f"sk={row.get('max_skewness')} ar={row.get('max_aspect_ratio')} "
            f"fw={row.get('min_face_weight')} t={row.get('elapsed_s')}",
            flush=True,
        )

    n_ok = sum(1 for row in rows if row.get("ok"))
    summary = {
        "total": len(rows),
        "ok": n_ok,
        "failed": len(rows) - n_ok,
        "run_root": str(args.run_root),
        "quality": args.quality,
        "max_cells": args.max_cells,
        "bl_layers": args.bl_layers,
    }
    (args.run_root / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
