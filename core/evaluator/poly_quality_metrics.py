"""Report-only Phase 0 metrics for polyhedral finite-volume cells.

The functions in this module deliberately do not participate in any quality
decision.  They provide measurements needed to calibrate the native_poly
quality gates without changing mesh generation or the existing gate metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.native_extensions import load_native_metrics


@dataclass(frozen=True)
class PolyPhase0Metrics:
    """Mesh-level summaries of the Phase 0 measurements.

    Face planar deviation is the maximum vertex distance from an
    area-weighted best-fit plane, divided by ``sqrt(face area)``.  Normal
    spread is the largest angle between a non-degenerate fan-triangle normal
    and that best-fit normal.  Cell metrics are summarized over all cells.
    """

    max_face_planar_deviation: float = 0.0
    mean_face_planar_deviation: float = 0.0
    p95_face_planar_deviation: float = 0.0
    max_face_normal_spread_deg: float = 0.0
    mean_face_normal_spread_deg: float = 0.0
    p95_face_normal_spread_deg: float = 0.0
    max_juretic_psi: float = 0.0
    mean_juretic_psi: float = 0.0
    p95_juretic_psi: float = 0.0
    min_cell_h: float = 0.0
    mean_cell_h: float = 0.0
    p95_cell_h: float = 0.0
    max_cell_h: float = 0.0
    min_circle_ratio: float = 0.0
    mean_circle_ratio: float = 0.0
    p95_circle_ratio: float = 0.0
    max_circle_ratio: float = 0.0
    min_sphericity: float = 0.0
    mean_sphericity: float = 0.0
    p95_sphericity: float = 0.0
    max_sphericity: float = 0.0
    min_uniformity_factor: float = 0.0
    mean_uniformity_factor: float = 0.0
    p95_uniformity_factor: float = 0.0
    max_uniformity_factor: float = 0.0
    min_face_pairing_residual: float = 0.0
    mean_face_pairing_residual: float = 0.0
    p95_face_pairing_residual: float = 0.0
    max_face_pairing_residual: float = 0.0


def _summary(values: list[float] | np.ndarray) -> tuple[float, float, float, float]:
    """Return min/mean/p95/max, with a stable zero for an empty population."""
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    return (
        float(arr.min()),
        float(arr.mean()),
        float(np.percentile(arr, 95.0)),
        float(arr.max()),
    )


def _minimum_pairing_sum_exhaustive(values: np.ndarray) -> float:
    """Small-input exact oracle for the native weighted-matching kernel."""
    norms = np.linalg.norm(values, axis=1)
    memo: dict[int, float] = {}

    def solve(mask: int) -> float:
        if mask == 0:
            return 0.0
        cached = memo.get(mask)
        if cached is not None:
            return cached
        first_bit = mask & -mask
        first = first_bit.bit_length() - 1
        rest = mask ^ first_bit
        best = float(norms[first]) + solve(rest)
        remaining = rest
        while remaining:
            second_bit = remaining & -remaining
            second = second_bit.bit_length() - 1
            pair = float(np.linalg.norm(values[first] + values[second]))
            best = min(best, pair + solve(rest ^ second_bit))
            remaining ^= second_bit
        memo[mask] = best
        return best

    return solve((1 << len(values)) - 1)


def _minimum_pairing_sum(vectors: np.ndarray) -> float:
    """Return the minimum unpaired-vector sum over deterministic pairings.

    A perfectly opposite pair contributes zero.  An odd face count leaves one
    vector unmatched and charges its magnitude; this keeps the diagnostic
    defined for arbitrary polyhedra without inventing a face.  The native path
    reduces the objective exactly to maximum-weight general matching.  The
    exhaustive fallback remains the source-build oracle for small cell sizes.
    """
    values = np.asarray(vectors, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("vectors must have shape (n, 3)")
    if len(values) == 0:
        return 0.0
    native_metrics = load_native_metrics()
    if native_metrics is not None and hasattr(native_metrics, "minimum_pairing_sum"):
        return float(native_metrics.minimum_pairing_sum(values))
    return _minimum_pairing_sum_exhaustive(values)


def _face_pairing_residual(
    face_normals: np.ndarray,
    face_areas: np.ndarray,
    incident_faces: list[int],
) -> float:
    """Juretić-style ``min pairing sum / total face area`` for one cell."""
    if not incident_faces:
        return 0.0
    ids = np.asarray(incident_faces, dtype=np.int64)
    normals = np.asarray(face_normals, dtype=np.float64)[ids]
    areas = np.asarray(face_areas, dtype=np.float64)[ids]
    valid = np.isfinite(normals).all(axis=1) & np.isfinite(areas) & (areas > 1.0e-30)
    if not np.any(valid):
        return 0.0
    vectors = normals[valid] * areas[valid, None]
    denominator = float(np.linalg.norm(vectors, axis=1).sum())
    if denominator <= 1.0e-30:
        return 0.0
    return float(np.clip(_minimum_pairing_sum(vectors) / denominator, 0.0, 1.0))


def _face_planarity_and_normal_spread(
    points: np.ndarray,
    face: list[int],
) -> tuple[float, float]:
    """Measure one polygon using an area-weighted fan fit.

    A fan from the first vertex supplies triangle areas and local normals.  A
    vertex receives one third of each incident triangle's area, giving an
    area-weighted centroid and covariance for the best-fit plane.  Absolute
    normal dot products make the result independent of face winding.
    """
    if len(face) < 3:
        return 0.0, 0.0

    vertices = points[np.asarray(face, dtype=np.int64)]
    n_vertices = len(vertices)
    weights = np.zeros(n_vertices, dtype=np.float64)
    local_normals: list[np.ndarray] = []
    local_areas: list[float] = []
    p0 = vertices[0]
    for i in range(1, n_vertices - 1):
        cross = np.cross(vertices[i] - p0, vertices[i + 1] - p0)
        area = 0.5 * float(np.linalg.norm(cross))
        if area <= 1.0e-30:
            continue
        weights[0] += area / 3.0
        weights[i] += area / 3.0
        weights[i + 1] += area / 3.0
        local_normals.append(cross / (2.0 * area))
        local_areas.append(area)

    total_area = float(sum(local_areas))
    if total_area <= 1.0e-30:
        return 0.0, 0.0

    weighted_centroid = np.average(vertices, axis=0, weights=weights)
    centered = vertices - weighted_centroid
    covariance = (centered * weights[:, np.newaxis]).T @ centered / float(weights.sum())
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    fit_normal = eigenvectors[:, int(np.argmin(eigenvalues))]
    fit_normal /= max(float(np.linalg.norm(fit_normal)), 1.0e-30)

    deviation = float(np.max(np.abs(centered @ fit_normal))) / np.sqrt(total_area)
    spreads: list[float] = []
    for normal in local_normals:
        cosine = float(np.clip(abs(np.dot(normal, fit_normal)), 0.0, 1.0))
        spreads.append(float(np.degrees(np.arccos(cosine))))
    normal_spread = max(spreads) if spreads else 0.0
    return deviation, normal_spread


def _juretic_psi(
    face_centres: np.ndarray,
    cell_centres: np.ndarray,
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_internal: int,
) -> np.ndarray:
    """Return Juretić's ``psi = |m| / |d|`` on internal faces.

    ``d`` is the owner-to-neighbour centre vector, ``x_f`` is the face
    centre, ``x_fi`` is the intersection of the centre line with the face
    plane in the usual face-centre approximation.  For an internal face this
    is exactly the existing native checker line-projection formula: its
    difference is reported separately from the boundary-face formula used by
    the current ``max_skewness`` gate.
    """
    count = min(int(n_internal), len(neighbour), len(owner), len(face_centres))
    if count <= 0:
        return np.empty(0, dtype=np.float64)

    own = np.asarray(owner[:count], dtype=np.int64)
    nbr = np.asarray(neighbour[:count], dtype=np.int64)
    valid_ids = (own >= 0) & (nbr >= 0) & (own < len(cell_centres)) & (nbr < len(cell_centres))
    if not np.any(valid_ids):
        return np.empty(0, dtype=np.float64)

    p_own = cell_centres[own[valid_ids]]
    p_nbr = cell_centres[nbr[valid_ids]]
    face = face_centres[:count][valid_ids]
    d = p_nbr - p_own
    d_mag = np.linalg.norm(d, axis=1)
    valid_d = d_mag > 1.0e-30
    if not np.any(valid_d):
        return np.empty(0, dtype=np.float64)

    p_own = p_own[valid_d]
    face = face[valid_d]
    d = d[valid_d]
    d_mag = d_mag[valid_d]
    t = np.einsum("ij,ij->i", face - p_own, d) / np.maximum(d_mag**2, 1.0e-60)
    intersection = p_own + t[:, np.newaxis] * d
    return np.linalg.norm(face - intersection, axis=1) / d_mag


def compute_poly_phase0_metrics(
    points: np.ndarray,
    faces: list[list[int]],
    owner: np.ndarray,
    neighbour: np.ndarray,
    n_internal: int,
    cell_centres: np.ndarray,
    face_centres: np.ndarray,
    face_normals: np.ndarray,
    face_areas: np.ndarray,
    cell_volumes: np.ndarray,
) -> PolyPhase0Metrics:
    """Compute report-only Phase 0 metrics for one polyMesh."""
    points = np.asarray(points, dtype=np.float64)
    cell_centres = np.asarray(cell_centres, dtype=np.float64)
    face_centres = np.asarray(face_centres, dtype=np.float64)
    face_normals = np.asarray(face_normals, dtype=np.float64)
    face_areas = np.asarray(face_areas, dtype=np.float64)
    cell_volumes = np.asarray(cell_volumes, dtype=np.float64)

    face_deviations: list[float] = []
    face_spreads: list[float] = []
    for face in faces:
        deviation, spread = _face_planarity_and_normal_spread(points, face)
        face_deviations.append(deviation)
        face_spreads.append(spread)

    face_dev_summary = _summary(face_deviations)
    face_spread_summary = _summary(face_spreads)
    psi_summary = _summary(_juretic_psi(face_centres, cell_centres, owner, neighbour, n_internal))

    cell_face_ids: list[list[int]] = [[] for _ in range(len(cell_centres))]
    for face_id, cell_id_raw in enumerate(np.asarray(owner, dtype=np.int64)[: len(faces)]):
        cell_id = int(cell_id_raw)
        if 0 <= cell_id < len(cell_face_ids):
            cell_face_ids[cell_id].append(face_id)
        if face_id < n_internal and face_id < len(neighbour):
            neighbour_id = int(neighbour[face_id])
            if 0 <= neighbour_id < len(cell_face_ids):
                cell_face_ids[neighbour_id].append(face_id)

    h_values: list[float] = []
    circle_ratios: list[float] = []
    sphericities: list[float] = []
    diameters: list[float] = []
    pairing_residuals: list[float] = []
    for cell_id, incident_faces in enumerate(cell_face_ids):
        if not incident_faces:
            continue
        vertex_ids = sorted({vertex for face_id in incident_faces for vertex in faces[face_id]})
        if len(vertex_ids) < 4:
            continue
        vertices = points[np.asarray(vertex_ids, dtype=np.int64)]
        pairing_residuals.append(
            _face_pairing_residual(face_normals, face_areas, incident_faces),
        )
        diameter = float(np.max(np.linalg.norm(vertices[:, np.newaxis] - vertices, axis=2)))
        diameters.append(diameter)

        area = float(np.sum(face_areas[np.asarray(incident_faces, dtype=np.int64)]))
        volume = abs(float(cell_volumes[cell_id])) if cell_id < len(cell_volumes) else 0.0
        if area > 1.0e-30:
            h_values.append(6.0 * volume / area)
            sphericity = (36.0 * np.pi * volume * volume) ** (1.0 / 3.0) / area
            sphericities.append(float(np.clip(sphericity, 0.0, 1.0)))
        else:
            h_values.append(0.0)
            sphericities.append(0.0)

        if diameter > 1.0e-30:
            centre = cell_centres[cell_id]
            circumradius = float(np.max(np.linalg.norm(vertices - centre, axis=1)))
            inradius = float("inf")
            for face_id in incident_faces:
                normal = face_normals[face_id]
                normal_mag = float(np.linalg.norm(normal))
                if normal_mag <= 1.0e-30:
                    continue
                distance = abs(float(np.dot(face_centres[face_id] - centre, normal / normal_mag)))
                inradius = min(inradius, distance)
            if not np.isfinite(inradius) or circumradius <= 1.0e-30:
                circle_ratios.append(0.0)
            else:
                circle_ratios.append(float(np.clip(inradius / circumradius, 0.0, 1.0)))
        else:
            circle_ratios.append(0.0)

    h_summary = _summary(h_values)
    circle_summary = _summary(circle_ratios)
    sphericity_summary = _summary(sphericities)
    if diameters:
        max_diameter = max(diameters)
        uniformity = np.asarray(diameters, dtype=np.float64) / max(max_diameter, 1.0e-30)
    else:
        uniformity = np.empty(0, dtype=np.float64)
    uniformity_summary = _summary(uniformity)
    pairing_summary = _summary(pairing_residuals)

    return PolyPhase0Metrics(
        max_face_planar_deviation=face_dev_summary[3],
        mean_face_planar_deviation=face_dev_summary[1],
        p95_face_planar_deviation=face_dev_summary[2],
        max_face_normal_spread_deg=face_spread_summary[3],
        mean_face_normal_spread_deg=face_spread_summary[1],
        p95_face_normal_spread_deg=face_spread_summary[2],
        max_juretic_psi=psi_summary[3],
        mean_juretic_psi=psi_summary[1],
        p95_juretic_psi=psi_summary[2],
        min_cell_h=h_summary[0],
        mean_cell_h=h_summary[1],
        p95_cell_h=h_summary[2],
        max_cell_h=h_summary[3],
        min_circle_ratio=circle_summary[0],
        mean_circle_ratio=circle_summary[1],
        p95_circle_ratio=circle_summary[2],
        max_circle_ratio=circle_summary[3],
        min_sphericity=sphericity_summary[0],
        mean_sphericity=sphericity_summary[1],
        p95_sphericity=sphericity_summary[2],
        max_sphericity=sphericity_summary[3],
        min_uniformity_factor=uniformity_summary[0],
        mean_uniformity_factor=uniformity_summary[1],
        p95_uniformity_factor=uniformity_summary[2],
        max_uniformity_factor=uniformity_summary[3],
        min_face_pairing_residual=pairing_summary[0],
        mean_face_pairing_residual=pairing_summary[1],
        p95_face_pairing_residual=pairing_summary[2],
        max_face_pairing_residual=pairing_summary[3],
    )
