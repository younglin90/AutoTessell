"""Report-only finite-volume MMS diagnostics for the native-poly quality lane.

This module is deliberately independent of the production dual generator.  It
provides a small cell-centred two-point-flux Laplacian on closed polyhedral
cells so ``POLY-FVERR-RANDPERT1`` can calibrate geometric metrics against a
solution error before any solver-specific gate is proposed.

The implementation is a diagnostic, not an OpenFOAM replacement: the
non-orthogonal correction is intentionally absent and the reported skew is an
explicit geometric proxy.  Production meshes must therefore be supplied by a
separate adapter and must not inherit these thresholds.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np


CellFaces = Sequence[Sequence[Sequence[int]]]


@dataclass(frozen=True)
class FvMmsLevel:
    """One refinement-level result for the manufactured Laplacian solution."""

    n_axis: int
    perturb_fraction: float
    n_cells: int
    max_non_ortho_deg: float
    max_skew_proxy: float
    l2_error: float
    linf_error: float


def build_cartesian_hex_grid(
    n_axis: int,
    *,
    perturb_fraction: float = 0.0,
    seed: int = 0,
) -> tuple[np.ndarray, list[list[list[int]]]]:
    """Build a unit-cube hex grid with deterministic interior perturbations."""

    n = int(n_axis)
    fraction = float(perturb_fraction)
    if n < 1:
        raise ValueError("n_axis must be positive")
    if not np.isfinite(fraction) or fraction < 0.0 or fraction > 0.25:
        raise ValueError("perturb_fraction must be in [0, 0.25]")

    axis = np.linspace(0.0, 1.0, n + 1, dtype=np.float64)
    points = np.empty(((n + 1) ** 3, 3), dtype=np.float64)

    def point_id(i: int, j: int, k: int) -> int:
        return (k * (n + 1) + j) * (n + 1) + i

    for k in range(n + 1):
        for j in range(n + 1):
            for i in range(n + 1):
                points[point_id(i, j, k)] = (axis[i], axis[j], axis[k])

    if fraction:
        rng = np.random.default_rng(int(seed))
        h = 1.0 / float(n)
        for k in range(1, n):
            for j in range(1, n):
                for i in range(1, n):
                    points[point_id(i, j, k)] += rng.uniform(
                        -fraction * h,
                        fraction * h,
                        size=3,
                    )

    cells: list[list[list[int]]] = []
    for k in range(n):
        for j in range(n):
            for i in range(n):
                p000 = point_id(i, j, k)
                p100 = point_id(i + 1, j, k)
                p110 = point_id(i + 1, j + 1, k)
                p010 = point_id(i, j + 1, k)
                p001 = point_id(i, j, k + 1)
                p101 = point_id(i + 1, j, k + 1)
                p111 = point_id(i + 1, j + 1, k + 1)
                p011 = point_id(i, j + 1, k + 1)
                cells.append(
                    [
                        [p000, p010, p110, p100],
                        [p001, p101, p111, p011],
                        [p000, p100, p101, p001],
                        [p010, p011, p111, p110],
                        [p000, p001, p011, p010],
                        [p100, p110, p111, p101],
                    ]
                )
    return points, cells


def _cell_geometry(
    points: np.ndarray,
    cell: Sequence[Sequence[int]],
) -> tuple[np.ndarray, float]:
    vertex_ids = sorted({int(vertex) for face in cell for vertex in face})
    center = points[np.asarray(vertex_ids, dtype=np.int64)].mean(axis=0)
    volume = 0.0
    for face in cell:
        if len(face) < 3:
            continue
        anchor = points[int(face[0])] - center
        for index in range(1, len(face) - 1):
            edge_a = points[int(face[index])] - center
            edge_b = points[int(face[index + 1])] - center
            volume += abs(float(np.dot(anchor, np.cross(edge_a, edge_b)))) / 6.0
    return center, float(volume)


def _face_geometry(
    points: np.ndarray,
    face: Sequence[int],
    cell_center: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    face_points = points[np.asarray(face, dtype=np.int64)]
    centroid = face_points.mean(axis=0)
    area_vector = np.zeros(3, dtype=np.float64)
    for index in range(len(face_points)):
        area_vector += np.cross(face_points[index], face_points[(index + 1) % len(face_points)])
    area_vector *= 0.5
    if float(np.dot(area_vector, centroid - cell_center)) < 0.0:
        area_vector = -area_vector
    area = float(np.linalg.norm(area_vector))
    return centroid, area_vector, area


def solve_laplacian_mms(
    points: np.ndarray,
    cell_faces: CellFaces,
    *,
    nonorthogonal_correction: bool = False,
) -> FvMmsLevel:
    """Solve ``-Δu=-6`` with exact Dirichlet data ``u=x²+y²+z²``.

    The default uses an orthogonal two-point flux coefficient.  When
    ``nonorthogonal_correction`` is enabled, a bounded deferred correction
    uses least-squares cell gradients; this remains diagnostic-only and is not
    an OpenFOAM-equivalent production discretization.  Both modes reject
    malformed/open cells and non-positive coefficients instead of silently
    producing an apparently valid convergence number.
    """

    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or not np.isfinite(pts).all():
        raise ValueError("points must be a finite (n, 3) array")
    cells = [
        [[int(vertex) for vertex in face] for face in cell]
        for cell in cell_faces
    ]
    if not cells:
        raise ValueError("cell_faces must not be empty")

    centers = np.empty((len(cells), 3), dtype=np.float64)
    volumes = np.empty(len(cells), dtype=np.float64)
    face_slots: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
    for cell_index, cell in enumerate(cells):
        centers[cell_index], volumes[cell_index] = _cell_geometry(pts, cell)
        if volumes[cell_index] <= 0.0 or not np.isfinite(volumes[cell_index]):
            raise ValueError("cell volume must be finite and positive")
        for face in cell:
            if len(face) < 3:
                raise ValueError("every face must have at least three vertices")
            if min(face) < 0 or max(face) >= len(pts):
                raise ValueError("face index is outside points")
            face_slots[tuple(sorted(face))].append((cell_index, face))

    import scipy.sparse  # noqa: PLC0415
    import scipy.sparse.linalg  # noqa: PLC0415

    matrix = scipy.sparse.lil_matrix((len(cells), len(cells)), dtype=np.float64)
    rhs = -6.0 * volumes
    face_data: list[tuple[int, int | None, np.ndarray, np.ndarray, np.ndarray, float | None]] = []
    max_non_ortho = 0.0
    max_skew = 0.0

    def exact(point: np.ndarray) -> float:
        return float(np.dot(point, point))

    for slots in face_slots.values():
        if len(slots) not in (1, 2):
            raise ValueError("face owner count must be one or two")
        first_index, first_face = slots[0]
        first_center = centers[first_index]
        face_center, area_vector, area = _face_geometry(pts, first_face, first_center)
        if area <= 0.0 or not np.isfinite(area):
            raise ValueError("face area must be finite and positive")

        if len(slots) == 2:
            second_index = slots[1][0]
            displacement = centers[second_index] - first_center
            denominator = float(np.dot(displacement, displacement))
            coefficient = float(np.dot(area_vector, displacement) / denominator)
            if coefficient <= 0.0 or not np.isfinite(coefficient):
                raise ValueError("non-positive internal two-point coefficient")
            matrix[first_index, first_index] += coefficient
            matrix[first_index, second_index] -= coefficient
            matrix[second_index, second_index] += coefficient
            matrix[second_index, first_index] -= coefficient

            distance = float(np.linalg.norm(displacement))
            normal_length = float(np.linalg.norm(area_vector))
            angle = np.degrees(
                np.arccos(
                    np.clip(
                        float(np.dot(area_vector, displacement))
                        / (normal_length * distance),
                        -1.0,
                        1.0,
                    )
                )
            )
            max_non_ortho = max(max_non_ortho, float(angle))
            projection = first_center + displacement * (
                float(np.dot(face_center - first_center, displacement)) / denominator
            )
            max_skew = max(
                max_skew,
                float(np.linalg.norm(face_center - projection) / distance),
            )
            face_data.append(
                (first_index, second_index, face_center, area_vector, displacement, None)
            )
        else:
            displacement = face_center - first_center
            denominator = float(np.dot(displacement, displacement))
            coefficient = float(np.dot(area_vector, displacement) / denominator)
            if coefficient <= 0.0 or not np.isfinite(coefficient):
                raise ValueError("non-positive boundary two-point coefficient")
            matrix[first_index, first_index] += coefficient
            boundary_value = exact(face_center)
            rhs[first_index] += coefficient * boundary_value
            face_data.append(
                (first_index, None, face_center, area_vector, displacement, boundary_value)
            )

    matrix_csr = matrix.tocsr()
    base_rhs = rhs.copy()
    solution = scipy.sparse.linalg.spsolve(matrix_csr, base_rhs)
    if nonorthogonal_correction:
        def gradients_from_solution(values: np.ndarray) -> np.ndarray:
            gradients = np.zeros((len(cells), 3), dtype=np.float64)
            for cell_index in range(len(cells)):
                normal_matrix = np.zeros((3, 3), dtype=np.float64)
                normal_rhs = np.zeros(3, dtype=np.float64)
                for left, right, face_point, _area_vector, _displacement, boundary_value in face_data:
                    if left != cell_index and right != cell_index:
                        continue
                    if right is None:
                        delta_x = face_point - centers[cell_index]
                        delta_u = float(boundary_value) - values[cell_index]
                    else:
                        other = right if left == cell_index else left
                        delta_x = centers[other] - centers[cell_index]
                        delta_u = values[other] - values[cell_index]
                    distance_sq = float(np.dot(delta_x, delta_x))
                    if distance_sq <= 0.0 or not np.isfinite(distance_sq):
                        continue
                    weight = 1.0 / distance_sq
                    normal_matrix += weight * np.outer(delta_x, delta_x)
                    normal_rhs += weight * delta_x * delta_u
                if np.linalg.matrix_rank(normal_matrix) < 3:
                    raise ValueError("least-squares gradient stencil is rank deficient")
                gradients[cell_index] = np.linalg.solve(normal_matrix, normal_rhs)
            return gradients

        for _ in range(8):
            gradients = gradients_from_solution(solution)
            correction = np.zeros(len(cells), dtype=np.float64)
            for left, right, face_point, area_vector, displacement, boundary_value in face_data:
                denominator = float(np.dot(displacement, displacement))
                if right is None:
                    grad_face = gradients[left]
                    delta_u = float(boundary_value) - solution[left]
                    grad_orth = displacement * (delta_u / denominator)
                    correction[left] += float(np.dot(grad_face - grad_orth, area_vector))
                    continue
                grad_face = 0.5 * (gradients[left] + gradients[right])
                delta_u = solution[right] - solution[left]
                grad_orth = displacement * (delta_u / denominator)
                face_correction = float(np.dot(grad_face - grad_orth, area_vector))
                correction[left] += face_correction
                correction[right] -= face_correction
            updated = scipy.sparse.linalg.spsolve(matrix_csr, base_rhs + correction)
            if not np.isfinite(updated).all():
                raise ValueError("non-orthogonal correction returned non-finite values")
            if float(np.linalg.norm(updated - solution, ord=np.inf)) < 1.0e-12:
                solution = updated
                break
            solution = updated
    if not np.isfinite(solution).all():
        raise ValueError("MMS solve returned non-finite values")
    exact_values = np.asarray([exact(center) for center in centers])
    error = solution - exact_values
    return FvMmsLevel(
        n_axis=round(len(cells) ** (1.0 / 3.0)),
        perturb_fraction=0.0,
        n_cells=len(cells),
        max_non_ortho_deg=float(max_non_ortho),
        max_skew_proxy=float(max_skew),
        l2_error=float(np.sqrt(np.sum(volumes * error * error) / np.sum(volumes))),
        linf_error=float(np.max(np.abs(error))),
    )


def run_laplacian_mms(
    levels: Sequence[int] = (4, 8, 16),
    *,
    perturb_fraction: float = 0.0,
    seed: int = 0,
    nonorthogonal_correction: bool = False,
) -> tuple[FvMmsLevel, ...]:
    """Run deterministic refinement levels for the report-only MMS census."""

    results: list[FvMmsLevel] = []
    for n_axis in levels:
        points, cells = build_cartesian_hex_grid(
            int(n_axis),
            perturb_fraction=perturb_fraction,
            seed=seed,
        )
        level = solve_laplacian_mms(
            points,
            cells,
            nonorthogonal_correction=nonorthogonal_correction,
        )
        results.append(
            FvMmsLevel(
                n_axis=int(n_axis),
                perturb_fraction=float(perturb_fraction),
                n_cells=level.n_cells,
                max_non_ortho_deg=level.max_non_ortho_deg,
                max_skew_proxy=level.max_skew_proxy,
                l2_error=level.l2_error,
                linf_error=level.linf_error,
            )
        )
    return tuple(results)


def convergence_orders(levels: Sequence[FvMmsLevel]) -> tuple[float, ...]:
    """Return base-2 L2 orders between consecutive refinement levels."""

    orders: list[float] = []
    for coarse, fine in zip(levels, levels[1:]):
        if coarse.l2_error <= 0.0 or fine.l2_error <= 0.0:
            orders.append(float("nan"))
        else:
            orders.append(float(np.log2(coarse.l2_error / fine.l2_error)))
    return tuple(orders)
