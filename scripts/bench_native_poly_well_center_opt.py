"""Diagnostic interior-vertex well-centeredness optimization.

This is deliberately a standalone experiment.  It keeps the native tet
connectivity and every boundary vertex fixed, and accepts a local move only
when incident circumcenter barycentric penalties improve without changing a
tet orientation or creating a near-zero volume.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault("AUTO_TESSELL_P4C_PYTETWILD", "0")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.readers import read_stl  # noqa: E402
from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402


def _boundary_vertices(tets: np.ndarray) -> set[int]:
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    for tet in tets.tolist():
        for face in ((tet[1], tet[2], tet[3]), (tet[0], tet[3], tet[2]),
                     (tet[0], tet[1], tet[3]), (tet[0], tet[2], tet[1])):
            counts[tuple(sorted(int(v) for v in face))] += 1
    return {v for face, count in counts.items() if count == 1 for v in face}


def _signed_volume6(points: np.ndarray, tet: np.ndarray) -> float:
    p = points[tet]
    return float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))


def _circumcenter_bary(points: np.ndarray, tet: np.ndarray) -> np.ndarray | None:
    p = points[tet]
    try:
        matrix = 2.0 * np.stack([p[i] - p[0] for i in (1, 2, 3)])
        rhs = np.asarray(
            [p[i] @ p[i] - p[0] @ p[0] for i in (1, 2, 3)], dtype=np.float64
        )
        center = np.linalg.solve(matrix, rhs)
        edge_matrix = np.column_stack([p[i] - p[0] for i in (1, 2, 3)])
        tail = np.linalg.solve(edge_matrix, center - p[0])
        bary = np.asarray([1.0 - tail.sum(), *tail], dtype=np.float64)
    except np.linalg.LinAlgError:
        return None
    if not np.isfinite(bary).all():
        return None
    return bary


def _census(points: np.ndarray, tets: np.ndarray) -> dict[str, float | int]:
    mins: list[float] = []
    for tet in tets:
        bary = _circumcenter_bary(points, tet)
        if bary is not None:
            mins.append(float(bary.min()))
    values = np.asarray(mins, dtype=np.float64)
    return {
        "tets": int(len(tets)),
        "finite": int(len(values)),
        "well_centered": int(np.count_nonzero(values >= -1e-10)),
        "well_centered_fraction": float(np.mean(values >= -1e-10)) if len(values) else 0.0,
        "min_barycentric": float(values.min()) if len(values) else 0.0,
        "negative_penalty": float(np.square(np.minimum(values, 0.0)).sum()) if len(values) else 0.0,
    }


def _local_objective(points: np.ndarray, tets: np.ndarray, incident: list[int]) -> tuple[float, int, float]:
    mins: list[float] = []
    for ti in incident:
        bary = _circumcenter_bary(points, tets[ti])
        if bary is not None:
            mins.append(float(bary.min()))
    if not mins:
        return float("inf"), 0, -float("inf")
    values = np.asarray(mins, dtype=np.float64)
    return (
        float(np.square(np.minimum(values, 0.0)).sum()),
        int(np.count_nonzero(values >= -1e-10)),
        float(values.min()),
    )


def _ep_tet_cost(points: np.ndarray, tet: np.ndarray, p: int = 2) -> float:
    local = points[tet]
    bary = _circumcenter_bary(points, tet)
    if bary is None:
        return 1e12
    try:
        matrix = 2.0 * np.stack([local[i] - local[0] for i in (1, 2, 3)])
        rhs = np.asarray([local[i] @ local[i] - local[0] @ local[0] for i in (1, 2, 3)])
        center = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return 1e12
    volume6 = abs(_signed_volume6(points, tet))
    if volume6 <= 1e-14:
        return 1e12
    values: list[float] = []
    for vertex in range(4):
        other = [index for index in range(4) if index != vertex]
        base = local[other]
        base_twice_area = float(np.linalg.norm(np.cross(base[1] - base[0], base[2] - base[0])))
        radius = float(np.linalg.norm(center - local[vertex]))
        if base_twice_area <= 1e-14 or radius <= 1e-14:
            return 1e12
        height = volume6 / base_twice_area
        values.append(abs(2.0 * height / radius - 1.0) ** p)
    return float(sum(values))


def _ep_local_objective(points: np.ndarray, tets: np.ndarray, incident: list[int]) -> tuple[float, int, float]:
    costs = [_ep_tet_cost(points, tets[ti]) for ti in incident]
    values = [_circumcenter_bary(points, tets[ti]) for ti in incident]
    finite = [float(bary.min()) for bary in values if bary is not None]
    return (
        float(sum(costs)),
        int(sum(value >= -1e-10 for value in finite)),
        min(finite) if finite else -float("inf"),
    )


def _optimize(
    points: np.ndarray,
    tets: np.ndarray,
    sweeps: int = 3,
    *,
    objective: str = "bary",
) -> tuple[np.ndarray, int]:
    out = points.copy()
    boundary = _boundary_vertices(tets)
    incident: dict[int, list[int]] = defaultdict(list)
    neighbours: dict[int, set[int]] = defaultdict(set)
    for ti, tet in enumerate(tets):
        for vertex in tet:
            vi = int(vertex)
            incident[vi].append(ti)
            neighbours[vi].update(int(other) for other in tet if int(other) != vi)
    signs = np.asarray([np.sign(_signed_volume6(out, tet)) for tet in tets])
    accepted = 0
    for _ in range(sweeps):
        for vi in sorted(set(range(len(out))) - boundary):
            incident_tets = incident[vi]
            if not incident_tets or not neighbours[vi]:
                continue
            objective_fn = _local_objective if objective == "bary" else _ep_local_objective
            before = objective_fn(out, tets, incident_tets)
            current = out[vi].copy()
            targets = [out[sorted(neighbours[vi])].mean(axis=0)]
            centers: list[np.ndarray] = []
            for ti in incident_tets:
                tet = tets[ti]
                bary = _circumcenter_bary(out, tet)
                if bary is None:
                    continue
                p = out[tet]
                try:
                    matrix = 2.0 * np.stack([p[i] - p[0] for i in (1, 2, 3)])
                    rhs = np.asarray([p[i] @ p[i] - p[0] @ p[0] for i in (1, 2, 3)])
                    centers.append(np.linalg.solve(matrix, rhs))
                except np.linalg.LinAlgError:
                    pass
            if centers:
                targets.append(np.mean(centers, axis=0))
            best = before
            best_position = current
            for target in targets:
                direction = target - current
                for fraction in (0.125, 0.25, 0.5, 0.75, 1.0):
                    candidate = current + fraction * direction
                    out[vi] = candidate
                    volumes = np.asarray([_signed_volume6(out, tets[ti]) for ti in incident_tets])
                    if np.any(np.abs(volumes) <= 1e-12) or np.any(np.sign(volumes) != signs[incident_tets]):
                        continue
                    score = objective_fn(out, tets, incident_tets)
                    if (score[0], -score[1], -score[2]) < (best[0], -best[1], -best[2]):
                        best = score
                        best_position = candidate.copy()
            out[vi] = best_position
            if best != before:
                accepted += 1
    return out, accepted


def main() -> None:
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(ROOT / "tests" / "benchmarks" / f"{shape}.stl")
        with tempfile.TemporaryDirectory(prefix="poly_well_center_opt_") as temp:
            primal = generate_native_tet(mesh.vertices, mesh.faces, Path(temp) / "primal", seed_density=6)
            if not primal.success or primal.tet_points is None or primal.tets is None:
                rows[shape] = {"success": False, "message": primal.message}
                continue
            before = np.asarray(primal.tet_points, dtype=np.float64)
            tets = np.asarray(primal.tets, dtype=np.int64)
            after, accepted = _optimize(before, tets, objective="bary")
            ep_after, ep_accepted = _optimize(before, tets, objective="ep")
            boundary = sorted(_boundary_vertices(tets))
            boundary_delta = float(np.max(np.abs(after[boundary] - before[boundary]))) if boundary else 0.0
            mode_rows: dict[str, object] = {}
            for mode, kwargs in (("centroid", {}), ("garimella", {"boundary_face_classifier": lambda tri, vertices: "defaultWall"})):
                result = tet_to_poly_dual(after, tets, Path(temp) / mode, _dual_point_mode=mode, **kwargs)
                mode_rows[mode] = {"invalid_cells": int(result.invalid_star_cells), "invalid_subtets": int(result.invalid_star_subtets), "message": result.message}
            ep_dual = tet_to_poly_dual(
                ep_after,
                tets,
                Path(temp) / "ep_garimella",
                _dual_point_mode="garimella",
                boundary_face_classifier=lambda tri, vertices: "defaultWall",
            )
            rows[shape] = {
                "points": int(len(before)),
                "tets": int(len(tets)),
                "boundary_vertices": len(boundary),
                "boundary_max_delta": boundary_delta,
                "accepted_moves": accepted,
                "before": _census(before, tets),
                "after": _census(after, tets),
                "ep_accepted_moves": ep_accepted,
                "ep_after": _census(ep_after, tets),
                "dual": mode_rows,
                "ep_garimella_candidate": {
                    "invalid_cells": int(ep_dual.invalid_star_cells),
                    "invalid_subtets": int(ep_dual.invalid_star_subtets),
                    "message": ep_dual.message,
                },
            }
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
