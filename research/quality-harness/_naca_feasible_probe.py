"""Measurement-only NACA boundary-skew feasibility probe.

Generates exactly one native-tet mesh, then compares two surface-locked apex
repositioning methods on independent in-memory copies.  No production code or
generated case under the repository is touched.
"""

from __future__ import annotations

import itertools
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

os.environ["AUTO_TESSELL_P4C_PYTETWILD"] = "0"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.analyzer.file_reader import load_mesh  # noqa: E402
from core.generator.native_tet.mesher import generate_native_tet  # noqa: E402
from core.utils.polymesh_reader import (  # noqa: E402
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)


NACA = ROOT / "tests" / "benchmarks" / "naca0012.stl"
TARGET_CELLS = 2000
N_WORST = 30
N_SWEEPS = 3
DEGEN_VOLUME = 1.0e-9
BACKTRACK = (1.0, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.001)


@dataclass(frozen=True)
class BoundaryRow:
    skew: float
    face: tuple[int, int, int]
    cell: int
    apex: int | None
    normal: np.ndarray
    centre: np.ndarray


@dataclass
class MeshState:
    points: np.ndarray
    tets: np.ndarray
    original_ids: np.ndarray


def _read_generated_mesh(poly: Path) -> tuple[np.ndarray, np.ndarray, set[int]]:
    points = np.asarray(parse_foam_points(poly / "points"), dtype=float)
    faces = [tuple(int(v) for v in f) for f in parse_foam_faces(poly / "faces")]
    owner = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    neighbour = np.asarray(parse_foam_labels(poly / "neighbour"), dtype=np.int64)
    n_internal = len(neighbour)
    n_cells = int(max(owner.max(), neighbour.max() if neighbour.size else 0)) + 1
    cell_vertices = [set() for _ in range(n_cells)]
    for face_i, face in enumerate(faces):
        cell_vertices[int(owner[face_i])].update(face)
        if face_i < n_internal:
            cell_vertices[int(neighbour[face_i])].update(face)
    bad = [cell_i for cell_i, verts in enumerate(cell_vertices) if len(verts) != 4]
    if bad:
        raise RuntimeError(f"Expected all tetrahedra; non-tet cells: {bad[:10]}")
    tets = np.asarray([sorted(verts) for verts in cell_vertices], dtype=np.int64)
    surface = {v for face in faces[n_internal:] for v in face}
    return points, tets, surface


def _signed_vol6(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    p = points[tets]
    return np.einsum(
        "ij,ij->i",
        p[:, 1] - p[:, 0],
        np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]),
    )


def _face_topology(
    tets: np.ndarray,
) -> tuple[list[tuple[int, int, int]], np.ndarray, np.ndarray, int]:
    incidence: dict[tuple[int, int, int], list[int]] = {}
    for cell, tet in enumerate(tets):
        for local_face in itertools.combinations((0, 1, 2, 3), 3):
            face = tuple(sorted(int(tet[i]) for i in local_face))
            incidence.setdefault(face, []).append(cell)
    internal = [(face, cells) for face, cells in incidence.items() if len(cells) >= 2]
    boundary = [(face, cells) for face, cells in incidence.items() if len(cells) == 1]
    faces = [item[0] for item in internal] + [item[0] for item in boundary]
    owner = np.asarray([item[1][0] for item in internal + boundary], dtype=np.int64)
    neighbour = np.asarray([item[1][1] for item in internal], dtype=np.int64)
    nonmanifold_faces = sum(len(cells) > 2 for cells in incidence.values())
    return faces, owner, neighbour, nonmanifold_faces


def _geometry(
    points: np.ndarray, tets: np.ndarray
) -> tuple[
    list[tuple[int, int, int]],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
]:
    faces, owner, neighbour, nonmanifold_faces = _face_topology(tets)
    face_points = points[np.asarray(faces, dtype=np.int64)]
    face_centres = face_points.mean(axis=1)
    face_normals = np.cross(
        face_points[:, 1] - face_points[:, 0],
        face_points[:, 2] - face_points[:, 0],
    )
    cell_centres = points[tets].mean(axis=1)
    return (
        faces,
        owner,
        neighbour,
        face_centres,
        face_normals,
        nonmanifold_faces,
    )


def _boundary_rows(
    points: np.ndarray,
    tets: np.ndarray,
    original_surface: set[int],
) -> list[BoundaryRow]:
    faces, owner, neighbour, face_centres, normals, _ = _geometry(points, tets)
    n_internal = len(neighbour)
    cell_centres = points[tets].mean(axis=1)
    rows: list[BoundaryRow] = []
    for face_i in range(n_internal, len(faces)):
        cell = int(owner[face_i])
        normal = normals[face_i]
        normal_mag = float(np.linalg.norm(normal))
        if normal_mag <= 1.0e-30:
            continue
        normal = normal / normal_mag
        to_face = face_centres[face_i] - cell_centres[cell]
        normal_distance = float(np.dot(to_face, normal))
        tangent = to_face - normal_distance * normal
        skew = float(np.linalg.norm(tangent) / max(abs(normal_distance), 1.0e-30))
        free = [int(v) for v in tets[cell] if int(v) not in original_surface]
        apex = free[0] if len(free) == 1 else None
        rows.append(
            BoundaryRow(
                skew,
                faces[face_i],
                cell,
                apex,
                normal,
                face_centres[face_i],
            )
        )
    return sorted(rows, key=lambda row: row.skew, reverse=True)


def _boundary_topology(tets: np.ndarray) -> dict[str, object]:
    faces, _, neighbour, nonmanifold_faces = _face_topology(tets)
    boundary = {faces[i] for i in range(len(neighbour), len(faces))}
    edge_counts: dict[tuple[int, int], int] = {}
    for face in boundary:
        for u, v in itertools.combinations(face, 2):
            edge = (u, v) if u < v else (v, u)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    vertices = {v for face in boundary for v in face}
    bad_edges = sum(count != 2 for count in edge_counts.values())
    euler = len(vertices) - len(edge_counts) + len(boundary)
    return {
        "faces": boundary,
        "n_faces": len(boundary),
        "bad_edges": bad_edges,
        "nonmanifold_faces": nonmanifold_faces,
        "euler": euler,
    }


def _metrics(
    state: MeshState,
    baseline_vol6: np.ndarray,
    original_surface: set[int],
    original_points: np.ndarray,
) -> dict[str, float | int]:
    points, tets = state.points, state.tets
    faces, owner, neighbour, face_centres, normals, _ = _geometry(points, tets)
    n_internal = len(neighbour)
    cell_centres = points[tets].mean(axis=1)

    internal_skew = 0.0
    non_ortho = 0.0
    if n_internal:
        own = owner[:n_internal]
        nbr = neighbour
        d = cell_centres[nbr] - cell_centres[own]
        d_mag = np.linalg.norm(d, axis=1)
        valid = d_mag > 1.0e-30
        if np.any(valid):
            diff = face_centres[:n_internal][valid] - cell_centres[own][valid]
            d_valid = d[valid]
            projection = cell_centres[own][valid] + (
                np.einsum("ij,ij->i", diff, d_valid) / d_mag[valid] ** 2
            )[:, None] * d_valid
            internal_skew = float(
                np.max(
                    np.linalg.norm(face_centres[:n_internal][valid] - projection, axis=1)
                    / d_mag[valid]
                )
            )
            normal_mag = np.linalg.norm(normals[:n_internal][valid], axis=1)
            valid_normal = normal_mag > 1.0e-30
            if np.any(valid_normal):
                cosine = np.abs(
                    np.einsum(
                        "ij,ij->i", d_valid[valid_normal], normals[:n_internal][valid][valid_normal]
                    )
                    / (d_mag[valid][valid_normal] * normal_mag[valid_normal])
                )
                non_ortho = float(np.degrees(np.arccos(np.clip(cosine, 0.0, 1.0))).max())

    rows = _boundary_rows(points, tets, original_surface)
    boundary_skew = rows[0].skew if rows else 0.0
    vol6 = _signed_vol6(points, tets)
    reference = baseline_vol6[state.original_ids]
    inversions = int(np.sum(np.sign(reference) * vol6 < 0.0))
    degen = int(np.sum(np.abs(vol6) / 6.0 < DEGEN_VOLUME))
    volume = float(np.sum(np.abs(vol6)) / 6.0)
    aligned_volume = float(np.sum(np.sign(reference) * vol6) / 6.0)
    surface_ids = np.asarray(sorted(original_surface), dtype=np.int64)
    surface_move = float(
        np.linalg.norm(points[surface_ids] - original_points[surface_ids], axis=1).max()
    )
    displacement = np.linalg.norm(points - original_points, axis=1)
    return {
        "cells": len(tets),
        "moved": int(np.sum(displacement > 1.0e-14)),
        "max_displacement": float(displacement.max()),
        "boundary_skew": boundary_skew,
        "internal_skew": internal_skew,
        "non_ortho": non_ortho,
        "inversions": inversions,
        "degen": degen,
        "volume": volume,
        "aligned_volume": aligned_volume,
        "surface_move": surface_move,
    }


def _vertex_to_tets(tets: np.ndarray) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for cell, tet in enumerate(tets):
        for vertex in tet:
            result.setdefault(int(vertex), []).append(cell)
    return result


def _tet_scales(points: np.ndarray, tets: np.ndarray) -> np.ndarray:
    p = points[tets]
    lengths = [np.linalg.norm(p[:, i] - p[:, j], axis=1) for i, j in itertools.combinations(range(4), 2)]
    return np.maximum(np.max(np.column_stack(lengths), axis=1), 1.0e-15)


def _orientation_margin(
    points: np.ndarray, tets: np.ndarray, incident: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    current = _signed_vol6(points, tets[incident])
    signs = np.sign(current)
    scales = _tet_scales(points, tets[incident])
    # Scale-relative floor, capped at 5% of current volume so current point is feasible.
    margins = np.minimum(1.0e-8 * scales**3, 0.05 * np.abs(current))
    return current, signs, margins


def _pick_row(
    points: np.ndarray,
    tets: np.ndarray,
    surface: set[int],
    pending: set[int],
) -> BoundaryRow | None:
    return next(
        (row for row in _boundary_rows(points, tets, surface) if row.apex in pending),
        None,
    )


def _tangential_recenter(
    baseline: MeshState,
    surface: set[int],
    candidates: set[int],
) -> tuple[MeshState, dict[str, int]]:
    state = MeshState(baseline.points.copy(), baseline.tets.copy(), baseline.original_ids.copy())
    v2t = _vertex_to_tets(state.tets)
    stats = {"attempted": 0, "accepted": 0}
    for _ in range(N_SWEEPS):
        pending = set(candidates)
        while pending:
            row = _pick_row(state.points, state.tets, surface, pending)
            if row is None or row.apex is None:
                break
            apex = row.apex
            pending.remove(apex)
            stats["attempted"] += 1
            x0 = state.points[apex].copy()
            to_face = row.centre - x0
            displacement = to_face - float(np.dot(to_face, row.normal)) * row.normal
            incident = np.asarray(v2t[apex], dtype=np.int64)
            _, signs, margins = _orientation_margin(state.points, state.tets, incident)
            for factor in BACKTRACK:
                trial = state.points.copy()
                trial[apex] = x0 + factor * displacement
                trial_vol6 = _signed_vol6(trial, state.tets[incident])
                if np.all(signs * trial_vol6 >= margins):
                    state.points[apex] = trial[apex]
                    stats["accepted"] += 1
                    break
    return state, stats


def _volume_affine_gradient(
    points: np.ndarray, tet: np.ndarray, apex: int, scale: float
) -> tuple[float, np.ndarray]:
    local = int(np.flatnonzero(tet == apex)[0])
    tet_points = points[tet].copy()

    def evaluate(x: np.ndarray) -> float:
        p = tet_points.copy()
        p[local] = x
        return float(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0])))

    x0 = points[apex]
    value = evaluate(x0)
    gradient = np.empty(3)
    for axis in range(3):
        shifted = x0.copy()
        shifted[axis] += scale
        gradient[axis] = (evaluate(shifted) - value) / scale
    return value, gradient


def _feasible_qp(
    baseline: MeshState,
    surface: set[int],
    candidates: set[int],
) -> tuple[MeshState, dict[str, int]]:
    state = MeshState(baseline.points.copy(), baseline.tets.copy(), baseline.original_ids.copy())
    v2t = _vertex_to_tets(state.tets)
    stats = {"attempted": 0, "accepted": 0, "failed": 0}
    for _ in range(N_SWEEPS):
        pending = set(candidates)
        while pending:
            row = _pick_row(state.points, state.tets, surface, pending)
            if row is None or row.apex is None:
                break
            apex = row.apex
            pending.remove(apex)
            stats["attempted"] += 1
            x0 = state.points[apex].copy()
            incident = np.asarray(v2t[apex], dtype=np.int64)
            _, signs, margins = _orientation_margin(state.points, state.tets, incident)
            local_scale = float(np.median(_tet_scales(state.points, state.tets[incident])))
            values = np.empty(len(incident))
            gradients = np.empty((len(incident), 3))
            for i, cell in enumerate(incident):
                values[i], gradients[i] = _volume_affine_gradient(
                    state.points, state.tets[cell], apex, local_scale
                )
            projector = np.eye(3) - np.outer(row.normal, row.normal)
            regularization = 1.0e-10

            def objective(x: np.ndarray) -> float:
                tangent = projector @ (x - row.centre)
                return float(
                    np.dot(tangent, tangent) / local_scale**2
                    + regularization * np.dot(x - x0, x - x0) / local_scale**2
                )

            def objective_jacobian(x: np.ndarray) -> np.ndarray:
                return (
                    2.0 * projector @ (x - row.centre) / local_scale**2
                    + 2.0 * regularization * (x - x0) / local_scale**2
                )

            constraints = {
                "type": "ineq",
                "fun": lambda x: signs
                * (values + gradients @ (x - x0))
                - margins,
                "jac": lambda _x: signs[:, None] * gradients,
            }
            result = minimize(
                objective,
                x0,
                jac=objective_jacobian,
                constraints=constraints,
                method="SLSQP",
                options={"ftol": 1.0e-12, "maxiter": 250, "disp": False},
            )
            feasibility = constraints["fun"](result.x)
            if (
                np.all(feasibility >= -1.0e-11 * local_scale**3)
                and objective(result.x) <= objective(x0) * (1.0 + 1.0e-8) + 1.0e-14
            ):
                state.points[apex] = result.x
                stats["accepted"] += 1
            else:
                stats["failed"] += 1
    return state, stats


def _collapse_candidate(
    state: MeshState, apex: int, keeper: int
) -> tuple[MeshState, int, int]:
    replaced = state.tets.copy()
    replaced[replaced == apex] = keeper
    replaced.sort(axis=1)
    valid = np.asarray([len(set(row)) == 4 for row in replaced], dtype=bool)
    collapsed_count = int(np.sum(~valid))
    replaced = replaced[valid]
    original_ids = state.original_ids[valid]
    _, unique_indices = np.unique(replaced, axis=0, return_index=True)
    keep = np.sort(unique_indices)
    duplicate_count = len(replaced) - len(keep)
    return (
        MeshState(state.points.copy(), replaced[keep], original_ids[keep]),
        collapsed_count,
        duplicate_count,
    )


def _apex_collapse_simulation(
    baseline: MeshState,
    baseline_vol6: np.ndarray,
    surface: set[int],
    candidates: set[int],
    original_points: np.ndarray,
) -> tuple[MeshState, dict[str, int]]:
    state = MeshState(baseline.points.copy(), baseline.tets.copy(), baseline.original_ids.copy())
    pending = set(candidates)
    stats = {"collapses": 0, "duplicate_vertex_cells": 0, "duplicate_cells": 0}
    while pending:
        row = _pick_row(state.points, state.tets, surface, pending)
        if row is None or row.apex is None:
            break
        apex = row.apex
        pending.remove(apex)
        options = []
        for keeper in row.face:
            trial, collapsed, duplicate = _collapse_candidate(state, apex, keeper)
            metrics = _metrics(trial, baseline_vol6, surface, original_points)
            score = (
                int(metrics["inversions"]),
                int(metrics["degen"]),
                float(metrics["boundary_skew"]),
                -int(metrics["cells"]),
            )
            options.append((score, trial, collapsed, duplicate))
        _, state, collapsed, duplicate = min(options, key=lambda item: item[0])
        stats["collapses"] += 1
        stats["duplicate_vertex_cells"] += collapsed
        stats["duplicate_cells"] += duplicate
        if float(_metrics(state, baseline_vol6, surface, original_points)["boundary_skew"]) < 50.0:
            break
    return state, stats


def _print_table(rows: list[tuple[str, dict[str, float | int]]], baseline_volume: float) -> None:
    print(
        "method        cells moved max_disp   bnd_skew int_skew nonortho inv degen "
        "vol_ratio surf_move"
    )
    for name, metrics in rows:
        print(
            f"{name:<13} {int(metrics['cells']):5d} {int(metrics['moved']):5d} "
            f"{float(metrics['max_displacement']):8.3g} "
            f"{float(metrics['boundary_skew']):9.3f} "
            f"{float(metrics['internal_skew']):8.3f} "
            f"{float(metrics['non_ortho']):8.3f} "
            f"{int(metrics['inversions']):3d} {int(metrics['degen']):5d} "
            f"{float(metrics['aligned_volume']) / baseline_volume:9.6f} "
            f"{float(metrics['surface_move']):9.2e}"
        )


def main() -> None:
    case = Path(tempfile.mkdtemp(prefix="nacaskew1_")) / "case"
    surface_mesh = load_mesh(NACA)
    result = generate_native_tet(
        np.asarray(surface_mesh.vertices, dtype=float),
        np.asarray(surface_mesh.faces, dtype=np.int64),
        case,
        target_cells=TARGET_CELLS,
    )
    poly = case / "constant" / "polyMesh"
    points, tets, surface = _read_generated_mesh(poly)
    baseline = MeshState(points.copy(), tets.copy(), np.arange(len(tets), dtype=np.int64))
    baseline_vol6 = _signed_vol6(points, tets)
    baseline_metrics = _metrics(baseline, baseline_vol6, surface, points)
    worst = _boundary_rows(points, tets, surface)[:N_WORST]
    candidates = {row.apex for row in worst if row.apex is not None}
    print(
        f"generation_calls=1 result_cells={result.n_cells} parsed_cells={len(tets)} "
        f"worst_faces={len(worst)} unique_apices={len(candidates)}"
    )
    print(
        f"worst30_single_apex={sum(row.apex is not None for row in worst)}/{len(worst)} "
        f"baseline_volume={float(baseline_metrics['volume']):.9f}"
    )

    tangential, tangential_stats = _tangential_recenter(baseline, surface, candidates)
    qp, qp_stats = _feasible_qp(baseline, surface, candidates)
    tangential_metrics = _metrics(tangential, baseline_vol6, surface, points)
    qp_metrics = _metrics(qp, baseline_vol6, surface, points)
    rows = [
        ("baseline", baseline_metrics),
        ("A_tangent", tangential_metrics),
        ("B_QP", qp_metrics),
    ]

    collapse_info: tuple[dict[str, int], dict[str, object], dict[str, object]] | None = None
    if (
        float(tangential_metrics["boundary_skew"]) >= 50.0
        and float(qp_metrics["boundary_skew"]) >= 50.0
    ):
        collapsed, collapse_stats = _apex_collapse_simulation(
            baseline, baseline_vol6, surface, candidates, points
        )
        collapse_metrics = _metrics(collapsed, baseline_vol6, surface, points)
        rows.append(("collapse_copy", collapse_metrics))
        collapse_info = (
            collapse_stats,
            _boundary_topology(baseline.tets),
            _boundary_topology(collapsed.tets),
        )

    _print_table(rows, float(baseline_metrics["volume"]))
    print(f"A_stats={tangential_stats}")
    print(f"B_stats={qp_stats}")
    if collapse_info is not None:
        collapse_stats, before, after = collapse_info
        changed = len(before["faces"] ^ after["faces"])
        print(
            "collapse_stats="
            f"{collapse_stats} boundary_faces={before['n_faces']}->{after['n_faces']} "
            f"surface_face_symmetric_diff={changed} bad_boundary_edges="
            f"{before['bad_edges']}->{after['bad_edges']} nonmanifold_faces="
            f"{before['nonmanifold_faces']}->{after['nonmanifold_faces']} "
            f"boundary_euler={before['euler']}->{after['euler']}"
        )


if __name__ == "__main__":
    main()
