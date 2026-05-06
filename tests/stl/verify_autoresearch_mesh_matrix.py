#!/usr/bin/env python3
"""Expanded mesh matrix verifier for codex-autoresearch.

The final stdout line is a JSON object. The primary metric is ``fail_count``,
defined as the total number of failed criteria across all cases. A zero value
means every STL/engine case passed every configured gate.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TARGET_CELLS = int(os.environ.get("AUTO_TESSELL_VERIFY_MAX_CELLS", "10000"))
BL_LAYERS = int(os.environ.get("AUTO_TESSELL_VERIFY_BL_LAYERS", "3"))
QUALITY = os.environ.get("AUTO_TESSELL_VERIFY_QUALITY", "fine")
TIMEOUT_S = float(os.environ.get("AUTO_TESSELL_VERIFY_TIMEOUT_S", "600"))
CASE_LIMIT = int(os.environ.get("AUTO_TESSELL_VERIFY_CASE_LIMIT", "0") or "0")
RUN_ROOT = Path(
    os.environ.get(
        "AUTO_TESSELL_VERIFY_RUN_ROOT",
        "/tmp/autotessell_autoresearch_verify_expanded",
    )
)

CELL_LOW = int(float(os.environ.get("AUTO_TESSELL_VERIFY_CELL_LOW_FACTOR", "0.5")) * TARGET_CELLS)
CELL_HIGH = int(float(os.environ.get("AUTO_TESSELL_VERIFY_CELL_HIGH_FACTOR", "2.0")) * TARGET_CELLS)
MAX_NON_ORTHO = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_NON_ORTHO", "65"))
MAX_BOUNDARY_SKEWNESS = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_BOUNDARY_SKEWNESS", "20"))
MAX_INTERNAL_SKEWNESS = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_INTERNAL_SKEWNESS", "4"))
MAX_CONCAVE = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_CONCAVE", "80"))
MIN_DETERMINANT = float(os.environ.get("AUTO_TESSELL_VERIFY_MIN_DETERMINANT", "0.001"))
MIN_FACE_WEIGHT = float(os.environ.get("AUTO_TESSELL_VERIFY_MIN_FACE_WEIGHT", "0.05"))
MIN_VOL_RATIO = float(os.environ.get("AUTO_TESSELL_VERIFY_MIN_VOL_RATIO", "0.01"))
MAX_ASPECT_RATIO = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_ASPECT_RATIO", "500"))
MAX_EXPANSION_RATIO = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_EXPANSION_RATIO", "1.5"))
MAX_HAUSDORFF_REL = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_HAUSDORFF_REL", "0.02"))
MAX_AREA_DEV_PCT = float(os.environ.get("AUTO_TESSELL_VERIFY_MAX_AREA_DEV_PCT", "2.0"))
SI_FACE_CAP = int(os.environ.get("AUTO_TESSELL_VERIFY_SI_FACE_CAP", "50000"))

ENGINES: dict[str, tuple[str, str]] = {
    "tet": ("tet", "wildmesh"),
    "hex": ("hex_dominant", "native_hex"),
    "poly": ("poly", "native_poly"),
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _as_float(value: Any, default: float = math.inf) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out):
            return default
        return out
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _dig(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _first_float(*values: Any, default: float = math.inf) -> float:
    for value in values:
        out = _as_float(value, default=math.nan)
        if not math.isnan(out):
            return out
    return default


def _stl_inputs() -> list[Path]:
    paths = [ROOT / "test_cube.stl"]
    paths.extend(sorted((ROOT / "tests" / "stl" / "thingi10k_bench20").glob("*.stl")))
    found = [p for p in paths if p.exists()]
    if CASE_LIMIT > 0:
        found = found[:CASE_LIMIT]
    return found


def _safe_case_name(stl_path: Path, engine: str) -> str:
    rel = stl_path.relative_to(ROOT).as_posix()
    return f"{rel.replace('/', '__').replace('.', '_')}__{engine}"


def _poly_paths(case_dir: Path) -> tuple[Path, Path, Path, Path, Path]:
    poly_dir = case_dir / "constant" / "polyMesh"
    return (
        poly_dir / "points",
        poly_dir / "faces",
        poly_dir / "owner",
        poly_dir / "neighbour",
        poly_dir / "boundary",
    )


def _load_poly_topology(case_dir: Path) -> dict[str, Any]:
    points_file, faces_file, owner_file, neighbour_file, boundary_file = _poly_paths(case_dir)
    if not all(p.exists() for p in (points_file, faces_file, owner_file, neighbour_file, boundary_file)):
        return {"available": False}

    try:
        from core.utils.polymesh_reader import (
            parse_foam_boundary,
            parse_foam_faces,
            parse_foam_labels,
            parse_foam_points,
        )

        points = np.asarray(parse_foam_points(points_file), dtype=np.float64)
        faces = [list(map(int, f)) for f in parse_foam_faces(faces_file)]
        owner = np.asarray(parse_foam_labels(owner_file), dtype=np.int64)
        neighbour = np.asarray(parse_foam_labels(neighbour_file), dtype=np.int64)
        patches = parse_foam_boundary(boundary_file)
    except Exception as exc:
        return {"available": False, "error": str(exc)[:200]}

    if points.size == 0 or not faces or owner.size == 0:
        return {"available": False, "error": "empty_polyMesh"}

    n_internal = int(neighbour.size)
    boundary_face_indices = list(range(n_internal, len(faces)))
    boundary_faces = [faces[i] for i in boundary_face_indices]
    degenerate_faces = 0
    duplicate_faces = 0
    edge_count: Counter[tuple[int, int]] = Counter()
    face_keys: Counter[tuple[int, ...]] = Counter()
    face_adjacency: dict[int, set[int]] = defaultdict(set)
    edge_to_faces: defaultdict[tuple[int, int], list[int]] = defaultdict(list)

    for local_idx, face in enumerate(boundary_faces):
        unique = list(dict.fromkeys(face))
        if len(unique) < 3:
            degenerate_faces += 1
            continue
        key = tuple(sorted(unique))
        face_keys[key] += 1
        for a, b in zip(unique, unique[1:] + unique[:1]):
            edge = (a, b) if a < b else (b, a)
            edge_count[edge] += 1
            edge_to_faces[edge].append(local_idx)

    duplicate_faces = sum(max(0, count - 1) for count in face_keys.values())
    for edge, attached in edge_to_faces.items():
        if len(attached) >= 2:
            for i in attached:
                face_adjacency[i].update(j for j in attached if j != i)

    visited: set[int] = set()
    components = 0
    for start in range(len(boundary_faces)):
        if start in visited:
            continue
        components += 1
        queue: deque[int] = deque([start])
        visited.add(start)
        while queue:
            cur = queue.popleft()
            for nxt in face_adjacency.get(cur, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)

    flipped_boundary_faces = _count_flipped_boundary_faces(points, faces, owner, neighbour)
    self_intersections = _count_boundary_self_intersections(points, boundary_faces)

    return {
        "available": True,
        "n_open_edges": int(sum(1 for c in edge_count.values() if c == 1)),
        "n_non_manifold_edges": int(sum(1 for c in edge_count.values() if c > 2)),
        "n_duplicate_faces": int(duplicate_faces),
        "n_degenerate_faces": int(degenerate_faces),
        "n_boundary_components": int(components),
        "n_flipped_faces": int(flipped_boundary_faces),
        "n_boundary_faces": int(len(boundary_faces)),
        "n_self_intersections": self_intersections,
        "patch_count": int(len(patches)),
        "patches": patches,
    }


def _face_centers(points: np.ndarray, faces: list[list[int]]) -> np.ndarray:
    centers = np.zeros((len(faces), 3), dtype=np.float64)
    for i, face in enumerate(faces):
        if face:
            centers[i] = points[np.asarray(face, dtype=np.int64)].mean(axis=0)
    return centers


def _face_normal(points: np.ndarray, face: list[int]) -> np.ndarray:
    if len(face) < 3:
        return np.zeros(3, dtype=np.float64)
    verts = points[np.asarray(face, dtype=np.int64)]
    base = verts[0]
    normal = np.zeros(3, dtype=np.float64)
    for i in range(1, len(verts) - 1):
        normal += np.cross(verts[i] - base, verts[i + 1] - base)
    norm = float(np.linalg.norm(normal))
    if norm <= 1e-30:
        return np.zeros(3, dtype=np.float64)
    return normal / norm


def _count_flipped_boundary_faces(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
) -> int:
    n_internal = int(neighbour.size)
    n_cells = int(max(owner.max(initial=0), neighbour.max(initial=0) if neighbour.size else 0) + 1)
    centers = _face_centers(points, faces)
    cell_centers = np.zeros((n_cells, 3), dtype=np.float64)
    counts = np.zeros(n_cells, dtype=np.int64)
    for face_idx, cell in enumerate(owner):
        if 0 <= int(cell) < n_cells:
            cell_centers[int(cell)] += centers[face_idx]
            counts[int(cell)] += 1
    for face_idx, cell in enumerate(neighbour):
        if 0 <= int(cell) < n_cells:
            cell_centers[int(cell)] += centers[face_idx]
            counts[int(cell)] += 1
    nz = counts > 0
    cell_centers[nz] /= counts[nz, None]

    flipped = 0
    for face_idx in range(n_internal, len(faces)):
        cell = int(owner[face_idx]) if face_idx < owner.size else -1
        if cell < 0 or cell >= n_cells:
            continue
        normal = _face_normal(points, faces[face_idx])
        if float(np.linalg.norm(normal)) <= 0.0:
            continue
        outward = centers[face_idx] - cell_centers[cell]
        if float(np.dot(normal, outward)) < -1e-12:
            flipped += 1
    return flipped


def _triangulate_boundary(boundary_faces: list[list[int]]) -> np.ndarray | None:
    tris: list[list[int]] = []
    for face in boundary_faces:
        unique = list(dict.fromkeys(face))
        if len(unique) < 3:
            continue
        for i in range(1, len(unique) - 1):
            tris.append([unique[0], unique[i], unique[i + 1]])
    if not tris:
        return None
    return np.asarray(tris, dtype=np.int64)


def _count_boundary_self_intersections(
    points: np.ndarray,
    boundary_faces: list[list[int]],
) -> int | None:
    tri_faces = _triangulate_boundary(boundary_faces)
    if tri_faces is None:
        return 0
    if tri_faces.shape[0] > SI_FACE_CAP:
        return None
    try:
        from core.preprocessor.native_repair.self_intersect import detect_self_intersections

        report = detect_self_intersections(points, tri_faces)
        return int(getattr(report, "n_intersections", len(getattr(report, "intersecting_face_pairs", []))))
    except Exception:
        return None


def _extract_input_components(geometry_report: dict[str, Any]) -> int | None:
    value = _dig(geometry_report, "geometry", "surface", "num_connected_components")
    try:
        return int(value)
    except Exception:
        return None


def _run_case(stl_path: Path, engine: str) -> dict[str, Any]:
    mesh_type, tier = ENGINES[engine]
    case_dir = RUN_ROOT / _safe_case_name(stl_path, engine)
    if case_dir.exists():
        shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "cli.main",
        "run",
        str(stl_path),
        "-o",
        str(case_dir),
        "--mesh-type",
        mesh_type,
        "--tier",
        tier,
        "--strict-tier",
        "--quality",
        QUALITY,
        "--checker-engine",
        "native",
        "--auto-retry",
        "off",
        "--max-cells",
        str(TARGET_CELLS),
        "--bl-layers",
        str(BL_LAYERS),
        "--tier-param",
        "post_layers_engine=auto",
        "--tier-param",
        f"post_layers_num_layers={BL_LAYERS}",
        "--tier-param",
        f"target_cells={TARGET_CELLS}",
        "--tier-param",
        f"max_cells={TARGET_CELLS}",
    ]
    env = os.environ.copy()
    env.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
    env.setdefault("AUTO_TESSELL_ALLOW_EXTERNAL_OPENFOAM", "0")
    # This verifier models the user-facing "exact BL layer count" path.  LCR is
    # still available for T-Rex-style narrow-gap reduction, but these bench cases
    # must generate the requested 3 layers rather than reporting auto-reduction.
    env.setdefault("AUTO_TESSELL_LCR_OFF", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")

    row: dict[str, Any] = {
        "stl": stl_path.relative_to(ROOT).as_posix(),
        "engine": engine,
        "mesh_type": mesh_type,
        "tier": tier,
        "case_dir": str(case_dir),
    }
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_S,
        )
        row["returncode"] = int(proc.returncode)
        row["elapsed_s"] = round(time.perf_counter() - start, 3)
        row["log_tail"] = proc.stdout[-3000:]
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        row.update(
            {
                "returncode": 124,
                "elapsed_s": round(time.perf_counter() - start, 3),
                "timeout": True,
                "log_tail": out[-3000:],
            }
        )
        return _classify(row, {}, {}, {}, {}, {}, {})

    return _classify(
        row,
        _read_json(case_dir / "quality_report.json"),
        _read_json(case_dir / "native_bl_quality.json"),
        _read_json(case_dir / "geometry_report.json"),
        _read_json(case_dir / "preprocessed_report.json"),
        _read_json(case_dir / "generator_log.json"),
        _load_poly_topology(case_dir),
    )


def _classify(
    row: dict[str, Any],
    quality_report: dict[str, Any],
    bl_quality: dict[str, Any],
    geometry_report: dict[str, Any],
    preprocessed_report: dict[str, Any],
    generator_log: dict[str, Any],
    topology: dict[str, Any],
) -> dict[str, Any]:
    del preprocessed_report
    summary = quality_report.get("evaluation_summary") or {}
    cm = summary.get("checkmesh") or {}
    fidelity = summary.get("geometry_fidelity") or {}
    add = summary.get("additional_metrics") or {}
    cell_stats = add.get("cell_volume_stats") or {}
    bl_stats = add.get("boundary_layer") or {}
    phase2 = add.get("native_bl_phase2") or {}
    lcr = bl_quality.get("lcr") or {}
    aniso_split = bl_quality.get("aniso_split") or {}
    wall_preserve = bl_quality.get("wall_preserve") or {}
    config = bl_quality.get("config") or {}

    row["verdict"] = summary.get("verdict")
    row["selected_tier"] = _dig(generator_log, "execution_summary", "selected_tier")
    row["cells"] = _as_int(cm.get("cells"))
    row["faces"] = _as_int(cm.get("faces"))
    row["points"] = _as_int(cm.get("points"))
    row["negative_volumes"] = _as_int(cm.get("negative_volumes"))
    row["min_face_area"] = _as_float(cm.get("min_face_area"), default=0.0)
    row["min_cell_volume"] = _as_float(cm.get("min_cell_volume"), default=0.0)
    row["min_determinant"] = _as_float(cm.get("min_determinant"))
    row["max_non_ortho"] = _as_float(cm.get("max_non_orthogonality"))
    row["max_skewness"] = _as_float(cm.get("max_skewness"))
    row["max_aspect_ratio"] = _as_float(cm.get("max_aspect_ratio"))
    row["max_boundary_skewness"] = _first_float(
        cm.get("max_boundary_skewness"),
        add.get("max_boundary_skewness"),
        default=row["max_skewness"],
    )
    row["max_internal_skewness"] = _first_float(
        cm.get("max_internal_skewness"),
        add.get("max_internal_skewness"),
        default=row["max_skewness"],
    )
    row["max_concavity"] = _first_float(
        cm.get("max_concavity"),
        add.get("max_concavity"),
        default=math.inf,
    )
    row["min_face_weight"] = _first_float(
        cm.get("min_face_weight"),
        add.get("min_face_weight"),
        default=math.inf,
    )
    max_adj_vol_ratio = _first_float(
        cm.get("max_adjacent_volume_ratio"),
        add.get("max_adjacent_volume_ratio"),
        add.get("max_adj_volume_ratio"),
        default=math.inf,
    )
    row["min_vol_ratio"] = _first_float(
        cm.get("min_vol_ratio"),
        add.get("min_vol_ratio"),
        default=(1.0 / max_adj_vol_ratio if max_adj_vol_ratio not in (0.0, math.inf) else math.inf),
    )
    row["max_expansion_ratio"] = _first_float(
        add.get("max_cell_size_growth_ratio"),
        add.get("max_expansion_ratio"),
        bl_stats.get("max_expansion_ratio"),
        config.get("growth_ratio"),
        default=math.inf,
    )
    row["max_face_warpage"] = _first_float(
        cm.get("max_face_warpage"),
        add.get("max_face_warpage"),
        add.get("max_face_twist"),
        default=math.inf,
    )
    row["hausdorff_relative"] = _as_float(fidelity.get("hausdorff_relative"))
    row["hausdorff_distance"] = _as_float(fidelity.get("hausdorff_distance"))
    row["surface_area_deviation_percent"] = _as_float(
        fidelity.get("surface_area_deviation_percent")
    )
    row["fidelity_rms"] = _first_float(fidelity.get("distance_rms"), fidelity.get("d_rms"), default=math.inf)
    row["fidelity_p95"] = _first_float(fidelity.get("distance_p95"), fidelity.get("d_95"), default=math.inf)
    row["fidelity_p99"] = _first_float(fidelity.get("distance_p99"), fidelity.get("d_99"), default=math.inf)
    row["normal_deviation_max_deg"] = _first_float(
        fidelity.get("normal_deviation_max_deg"),
        fidelity.get("max_normal_deviation_deg"),
        default=math.inf,
    )
    row["feature_preservation_score"] = _first_float(
        fidelity.get("feature_preservation_score"),
        default=math.inf,
    )
    row["n_self_intersect_pre"] = fidelity.get("n_self_intersect_pre")
    row["bl_prisms"] = _as_int(
        bl_quality.get("n_prism_cells")
        or phase2.get("n_prism_cells")
        or 0
    )
    row["bl_requested_layers"] = _as_int(
        bl_quality.get("requested_layers") or config.get("num_layers") or BL_LAYERS
    )
    row["bl_used_layers"] = _as_int(
        bl_quality.get("used_layers") or config.get("num_layers") or phase2.get("lcr_min_layers_used") or 0
    )
    row["lcr_min_layers_used"] = _as_int(
        lcr.get("min_layers_used") or phase2.get("lcr_min_layers_used") or row["bl_used_layers"]
    )
    row["n_degenerate_prisms"] = _as_int(
        bl_quality.get("n_degenerate_prisms") or phase2.get("n_degenerate_prisms") or 0
    )
    row["bl_wall_preserve"] = bool(wall_preserve.get("within_envelope", False))
    row["bl_wall_max_diff_rel"] = _as_float(wall_preserve.get("max_diff_rel"), default=math.inf)
    row["aniso_split_examined"] = _as_int(
        aniso_split.get("n_examined") or phase2.get("aniso_split_n_examined") or 0
    )
    row["topology"] = topology
    input_components = _extract_input_components(geometry_report)
    row["input_components"] = input_components

    failures: list[str] = []
    missing_metrics: list[str] = []

    def fail_if(cond: bool, name: str) -> None:
        if cond:
            failures.append(name)

    def require_metric(value: Any, name: str) -> None:
        if value is None:
            missing_metrics.append(name)
            return
        if isinstance(value, float) and math.isinf(value):
            missing_metrics.append(name)

    fail_if(row.get("returncode") != 0, "cli_returncode")
    fail_if(bool(row.get("timeout")), "timeout")
    fail_if(row.get("verdict") != "PASS", "verdict")
    fail_if(row["selected_tier"] and row["tier"] not in str(row["selected_tier"]), "fallback_or_wrong_tier")
    fail_if(row["cells"] <= 0, "zero_cells")
    fail_if(not (CELL_LOW <= row["cells"] <= CELL_HIGH), "cell_count")
    fail_if(row["negative_volumes"] != 0, "negative_volumes")
    fail_if(row["min_cell_volume"] <= 1e-30, "near_zero_cell_volume")
    fail_if(row["min_face_area"] <= 1e-30, "near_zero_face_area")
    fail_if(row["max_non_ortho"] > MAX_NON_ORTHO, "non_ortho")
    fail_if(row["max_boundary_skewness"] > MAX_BOUNDARY_SKEWNESS, "boundary_skewness")
    fail_if(row["max_internal_skewness"] > MAX_INTERNAL_SKEWNESS, "internal_skewness")
    fail_if(row["max_aspect_ratio"] > MAX_ASPECT_RATIO, "aspect_ratio")
    fail_if(row["min_determinant"] < MIN_DETERMINANT, "determinant")
    fail_if(row["max_concavity"] > MAX_CONCAVE, "concavity")
    fail_if(row["min_face_weight"] < MIN_FACE_WEIGHT, "face_weight")
    fail_if(row["min_vol_ratio"] < MIN_VOL_RATIO, "adjacent_volume_ratio")
    fail_if(row["max_expansion_ratio"] > MAX_EXPANSION_RATIO, "expansion_ratio")
    fail_if(row["max_face_warpage"] > 1e-6 and row["max_face_warpage"] != math.inf, "face_warpage")
    fail_if(row["hausdorff_relative"] > MAX_HAUSDORFF_REL, "hausdorff")
    fail_if(row["surface_area_deviation_percent"] > MAX_AREA_DEV_PCT, "surface_area")
    fail_if(row["bl_prisms"] <= 0, "missing_bl")
    fail_if(row["bl_requested_layers"] != BL_LAYERS, "wrong_requested_bl_layers")
    fail_if(row["bl_used_layers"] != BL_LAYERS, "wrong_used_bl_layers")
    fail_if(row["lcr_min_layers_used"] != BL_LAYERS, "lcr_reduced_layers")
    fail_if(row["n_degenerate_prisms"] != 0, "degenerate_prisms")
    fail_if(not row["bl_wall_preserve"], "bl_wall_drift")
    fail_if(row["bl_wall_max_diff_rel"] > 1e-6, "bl_wall_drift_rel")

    require_metric(row["max_concavity"], "max_concavity")
    require_metric(row["min_face_weight"], "min_face_weight")
    require_metric(row["min_vol_ratio"], "min_vol_ratio")
    require_metric(row["max_expansion_ratio"], "max_expansion_ratio")
    require_metric(row["max_face_warpage"], "max_face_warpage")
    require_metric(row["fidelity_rms"], "fidelity_rms")
    require_metric(row["fidelity_p95"], "fidelity_p95")
    require_metric(row["fidelity_p99"], "fidelity_p99")
    require_metric(row["normal_deviation_max_deg"], "normal_deviation")
    require_metric(row["feature_preservation_score"], "feature_preservation")

    if not topology.get("available"):
        failures.append("missing_topology")
    else:
        fail_if(_as_int(topology.get("n_open_edges")) != 0, "open_edges")
        fail_if(_as_int(topology.get("n_non_manifold_edges")) != 0, "non_manifold_edges")
        fail_if(_as_int(topology.get("n_duplicate_faces")) != 0, "duplicate_faces")
        fail_if(_as_int(topology.get("n_degenerate_faces")) != 0, "degenerate_boundary_faces")
        fail_if(_as_int(topology.get("n_flipped_faces")) != 0, "flipped_boundary_faces")
        if topology.get("n_self_intersections") is None:
            missing_metrics.append("boundary_self_intersections")
        else:
            fail_if(_as_int(topology.get("n_self_intersections")) != 0, "boundary_self_intersections")
        if input_components is not None:
            fail_if(
                _as_int(topology.get("n_boundary_components")) != int(input_components),
                "unexpected_disconnected_components",
            )
        else:
            missing_metrics.append("input_connected_components")
        fail_if(_as_int(topology.get("patch_count")) <= 0, "missing_patch_topology")

    failures.extend(f"missing_metric:{name}" for name in sorted(set(missing_metrics)))
    row["metric_gap_count"] = len(set(missing_metrics))
    row["failures"] = failures
    row["failure_count"] = len(failures)
    row["ok"] = not failures
    return row


def _status_line(row: dict[str, Any]) -> str:
    status = "OK" if row["ok"] else "FAIL:" + ",".join(row["failures"][:6])
    if len(row["failures"]) > 6:
        status += f",...(+{len(row['failures']) - 6})"
    return (
        f"{status} {row['stl']} {row['engine']} cells={row.get('cells')} "
        f"no={row.get('max_non_ortho'):.1f} sk={row.get('max_skewness'):.2f} "
        f"ar={row.get('max_aspect_ratio'):.1f} h={row.get('hausdorff_relative'):.4f} "
        f"bl={row.get('bl_used_layers')}/{BL_LAYERS}"
    )


def main() -> int:
    if RUN_ROOT.exists():
        shutil.rmtree(RUN_ROOT, ignore_errors=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    inputs = _stl_inputs()
    for stl_path in inputs:
        for engine in ("tet", "hex", "poly"):
            row = _run_case(stl_path, engine)
            rows.append(row)
            print(_status_line(row), flush=True)

    failure_reasons: Counter[str] = Counter()
    for row in rows:
        failure_reasons.update(row["failures"])

    failed_cases = sum(1 for row in rows if not row["ok"])
    fail_count = sum(int(row["failure_count"]) for row in rows)
    summary = {
        "fail_count": fail_count,
        "failed_case_count": failed_cases,
        "total_cases": len(rows),
        "pass_count": len(rows) - failed_cases,
        "tet_failed_case_count": sum(1 for row in rows if row["engine"] == "tet" and not row["ok"]),
        "hex_failed_case_count": sum(1 for row in rows if row["engine"] == "hex" and not row["ok"]),
        "poly_failed_case_count": sum(1 for row in rows if row["engine"] == "poly" and not row["ok"]),
        "metric_gap_count": sum(int(row.get("metric_gap_count", 0)) for row in rows),
        "timeout_count": sum(1 for row in rows if row.get("timeout")),
        "max_non_ortho": max((_as_float(row.get("max_non_ortho"), 0.0) for row in rows), default=0.0),
        "max_skewness": max((_as_float(row.get("max_skewness"), 0.0) for row in rows), default=0.0),
        "max_aspect_ratio": max((_as_float(row.get("max_aspect_ratio"), 0.0) for row in rows), default=0.0),
        "max_hausdorff_relative": max((_as_float(row.get("hausdorff_relative"), 0.0) for row in rows), default=0.0),
        "target_cells": TARGET_CELLS,
        "cell_low": CELL_LOW,
        "cell_high": CELL_HIGH,
        "bl_layers": BL_LAYERS,
        "quality": QUALITY,
        "timeout_s": TIMEOUT_S,
        "failure_reasons": dict(failure_reasons.most_common()),
        "rows_path": str((ROOT / "autoresearch-results" / "verify_last.json").resolve()),
    }
    out_path = ROOT / "autoresearch-results" / "verify_last.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
