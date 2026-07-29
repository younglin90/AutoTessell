"""Report-only primal relocation driven by dual internal-face warpage.

The experiment keeps tet connectivity and all boundary vertices fixed.  It
uses centroid tet-dual points and accepts a small interior move only when the
affected closed internal rings become more planar and every incident tet keeps
its orientation and nonzero volume.  It is not connected to production.
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
from core.generator.native_poly.dual import (  # noqa: E402
    _build_tet_topology,
    _extract_boundary,
    _ordered_tet_ring,
    tet_to_poly_dual,
)
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402


def _boundary_vertices(face_tets: dict[tuple[int, int, int], list[int]]) -> set[int]:
    return {v for face, owners in face_tets.items() if len(owners) == 1 for v in face}


def _boundary_edges(face_tets: dict[tuple[int, int, int], list[int]]) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for face, owners in face_tets.items():
        if len(owners) != 1:
            continue
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            result.add((min(a, b), max(a, b)))
    return result


def _warpage(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    center = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - center, full_matrices=False)
    scale = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    if scale <= 1e-14:
        return 0.0
    return float(np.max(np.abs((points - center) @ vh[-1])) / scale)


def _signed_volume6(points: np.ndarray, tet: np.ndarray) -> float:
    p = points[tet]
    return float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))


def _ring_data(
    points: np.ndarray, tets: np.ndarray,
) -> tuple[dict[tuple[int, int], list[int]], set[tuple[int, int]], dict[tuple[int, int], float]]:
    _, edge_tets, face_tets = _build_tet_topology(tets, len(points))
    boundary_edges = _boundary_edges(face_tets)
    rings: dict[tuple[int, int], list[int]] = {}
    values: dict[tuple[int, int], float] = {}
    for edge in edge_tets:
        if edge in boundary_edges:
            continue
        ring, closed = _ordered_tet_ring(edge, edge_tets, face_tets, tets)
        if closed and len(ring) >= 3:
            rings[edge] = ring
            values[edge] = _warpage(points[tets[np.asarray(ring, dtype=np.int64)]].mean(axis=1))
    return edge_tets, boundary_edges, values


def _objective(values: dict[tuple[int, int], float], edges: set[tuple[int, int]] | None = None) -> float:
    selected = values if edges is None else {e: values[e] for e in edges if e in values}
    return float(sum(value * value for value in selected.values()))


def _optimize(points: np.ndarray, tets: np.ndarray, sweeps: int = 2) -> tuple[np.ndarray, int, dict[str, float]]:
    out = points.copy()
    _, _, before_values = _ring_data(out, tets)
    before_global = _objective(before_values)
    _, _, face_tets = _build_tet_topology(tets, len(out))
    boundary = _boundary_vertices(face_tets)
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
            incident_tets = incident.get(vi, [])
            if not incident_tets or not neighbours.get(vi):
                continue
            affected_edges: set[tuple[int, int]] = set()
            for ti in incident_tets:
                tet = tets[ti]
                for a, b in ((tet[0], tet[1]), (tet[0], tet[2]), (tet[0], tet[3]),
                              (tet[1], tet[2]), (tet[1], tet[3]), (tet[2], tet[3])):
                    edge = (min(int(a), int(b)), max(int(a), int(b)))
                    affected_edges.add(edge)
            _, _, current_values = _ring_data(out, tets)
            current = _objective(current_values, affected_edges)
            old_position = out[vi].copy()
            target = out[sorted(neighbours[vi])].mean(axis=0)
            best_score = current
            best_position = old_position
            for fraction in (0.125, 0.25, 0.5):
                out[vi] = old_position + fraction * (target - old_position)
                volumes = np.asarray([_signed_volume6(out, tets[ti]) for ti in incident_tets])
                if np.any(np.abs(volumes) <= 1e-12) or np.any(np.sign(volumes) != signs[incident_tets]):
                    continue
                _, _, candidate_values = _ring_data(out, tets)
                candidate = _objective(candidate_values, affected_edges)
                if candidate + 1e-14 < best_score:
                    best_score = candidate
                    best_position = out[vi].copy()
            out[vi] = best_position
            if not np.array_equal(best_position, old_position):
                accepted += 1
    _, _, after_values = _ring_data(out, tets)
    return out, accepted, {
        "warpage_sq_before": before_global,
        "warpage_sq_after": _objective(after_values),
        "max_before": max(before_values.values()) if before_values else 0.0,
        "max_after": max(after_values.values()) if after_values else 0.0,
        "mean_before": float(np.mean(list(before_values.values()))) if before_values else 0.0,
        "mean_after": float(np.mean(list(after_values.values()))) if after_values else 0.0,
    }


def main() -> None:
    rows: dict[str, object] = {}
    for shape in ("cube", "cylinder", "sphere"):
        mesh = read_stl(ROOT / "tests" / "benchmarks" / f"{shape}.stl")
        with tempfile.TemporaryDirectory(prefix="native_poly_face_aware_") as temp:
            primal = generate_native_tet(mesh.vertices, mesh.faces, Path(temp) / "primal", seed_density=6)
            if not primal.success or primal.tet_points is None or primal.tets is None:
                rows[shape] = {"success": False, "message": primal.message}
                continue
            before = np.asarray(primal.tet_points, dtype=np.float64)
            tets = np.asarray(primal.tets, dtype=np.int64)
            after, accepted, metrics = _optimize(before, tets)
            boundary = sorted(_boundary_vertices(_build_tet_topology(tets, len(tets))[2]))
            boundary_delta = float(np.max(np.abs(after[boundary] - before[boundary]))) if boundary else 0.0
            base = tet_to_poly_dual(before, tets, Path(temp) / "base", _dual_point_mode="centroid")
            candidate = tet_to_poly_dual(after, tets, Path(temp) / "candidate", _dual_point_mode="centroid")
            rows[shape] = {
                "success": True,
                "points": int(len(before)),
                "tets": int(len(tets)),
                "accepted_moves": int(accepted),
                "boundary_max_delta": boundary_delta,
                **metrics,
                "dual_invalid_cells_before_after": [int(base.invalid_star_cells), int(candidate.invalid_star_cells)],
                "dual_invalid_subtets_before_after": [int(base.invalid_star_subtets), int(candidate.invalid_star_subtets)],
                "candidate_success": bool(candidate.success),
            }
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
