"""tet mesh → polyhedral dual mesh 자체 구현.

OpenFOAM ``polyDualMesh`` 와 동일한 개념:

    입력 tet mesh (V_in, T_in) 에 대해
      - internal input vertex v_i → dual cell C_i
      - dual cell 의 vertex 집합 = v_i 를 포함하는 모든 tet 의 centroid
      - dual cell 의 face 는 ConvexHull 로 생성 (같은 평면상의 triangle 은 polygon
        으로 병합)
      - boundary input vertex 는 surface 위에 그대로 남고, 인접 boundary face
        centroid 를 dual vertex 로 추가

본 MVP 는 internal vertex 만 dual cell 로 취급하고, boundary vertex 주위의 cell
은 surface patch 를 닫는 polygon 으로 마감한다. 결과는 OpenFOAM polyMesh 에 직접
기록 (핵심 face-list 형식).

제약:
    - 입력 tet mesh 는 watertight 하다고 가정.
    - degenerate tet 은 미리 제거되어야 함.
    - boundary vertex 주위 dual cell 은 "vertex + 인접 tet centroid + 인접
      boundary face centroid + 인접 boundary edge midpoint" 의 ConvexHull 로 생성.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Any, cast

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PolyDualResult:
    success: bool
    elapsed: float
    n_cells: int = 0
    n_points: int = 0
    n_faces: int = 0
    message: str = ""
    invalid_star_cells: int = 0
    invalid_star_subtets: int = 0
    star_examples: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class TetPrimalConformityAudit:
    """Deterministic conformal-complex census for a tetrahedral primal."""

    duplicate_tet_groups: tuple[tuple[tuple[int, int, int, int], tuple[int, ...]], ...]
    nonmanifold_face_groups: tuple[tuple[tuple[int, int, int], tuple[int, ...]], ...]
    negative_orientation_rows: tuple[int, ...]
    orphan_vertex_rows: tuple[int, ...]

    @property
    def conformal(self) -> bool:
        return (
            not self.duplicate_tet_groups
            and not self.nonmanifold_face_groups
            and not self.orphan_vertex_rows
        )


def _audit_tet_primal_conformity_python(
    points: np.ndarray,
    tets: np.ndarray,
) -> TetPrimalConformityAudit:
    """Independent sort/run oracle for primal tetrahedral conformity."""
    tet_records = sorted(
        (
            cast(
                tuple[int, int, int, int],
                tuple(sorted(int(vertex) for vertex in tet)),
            ),
            index,
        )
        for index, tet in enumerate(tets)
    )
    duplicate_groups: list[tuple[tuple[int, int, int, int], tuple[int, ...]]] = []
    begin = 0
    while begin < len(tet_records):
        end = begin + 1
        while end < len(tet_records) and tet_records[end][0] == tet_records[begin][0]:
            end += 1
        if end - begin > 1:
            duplicate_groups.append(
                (
                    tet_records[begin][0],
                    tuple(record[1] for record in tet_records[begin:end]),
                )
            )
        begin = end

    local_faces = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))
    face_records = sorted(
        (
            cast(
                tuple[int, int, int],
                tuple(sorted(int(tet[local]) for local in face)),
            ),
            tet_index,
        )
        for tet_index, tet in enumerate(tets)
        for face in local_faces
    )
    nonmanifold_groups: list[tuple[tuple[int, int, int], tuple[int, ...]]] = []
    begin = 0
    while begin < len(face_records):
        end = begin + 1
        while end < len(face_records) and face_records[end][0] == face_records[begin][0]:
            end += 1
        if end - begin > 2:
            nonmanifold_groups.append(
                (
                    face_records[begin][0],
                    tuple(record[1] for record in face_records[begin:end]),
                )
            )
        begin = end

    tet_points = points[tets]
    signed_volume6 = np.einsum(
        "ij,ij->i",
        tet_points[:, 1] - tet_points[:, 0],
        np.cross(tet_points[:, 2] - tet_points[:, 0], tet_points[:, 3] - tet_points[:, 0]),
    )
    negative_rows = tuple(int(row) for row in np.flatnonzero(signed_volume6 < 0.0))
    incident_vertices = np.zeros(points.shape[0], dtype=bool)
    incident_vertices[tets.reshape(-1)] = True
    orphan_rows = tuple(int(row) for row in np.flatnonzero(~incident_vertices))
    return TetPrimalConformityAudit(
        tuple(duplicate_groups),
        tuple(nonmanifold_groups),
        negative_rows,
        orphan_rows,
    )


def _normalise_tet_primal_conformity_audit(
    result: Any,
    *,
    n_points: int,
    n_tets: int,
) -> TetPrimalConformityAudit:
    """Validate an optional native result before it can certify the primal."""

    def _exact_int(value: Any) -> int:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
            raise TypeError("native conformity fields must be integer")
        return int(value)

    try:
        raw_duplicates, raw_nonmanifold, raw_negative, raw_orphans = result
        if (
            not isinstance(raw_orphans, np.ndarray)
            or raw_orphans.dtype != np.dtype(np.int64)
            or raw_orphans.ndim != 1
            or not raw_orphans.flags.c_contiguous
        ):
            raise TypeError("native orphan rows must be a contiguous int64 vector")
        duplicates = tuple(
            (
                cast(
                    tuple[int, int, int, int],
                    tuple(_exact_int(vertex) for vertex in key),
                ),
                tuple(_exact_int(owner) for owner in owners),
            )
            for key, owners in raw_duplicates
        )
        nonmanifold = tuple(
            (
                cast(
                    tuple[int, int, int],
                    tuple(_exact_int(vertex) for vertex in key),
                ),
                tuple(_exact_int(owner) for owner in owners),
            )
            for key, owners in raw_nonmanifold
        )
        negative = tuple(_exact_int(row) for row in raw_negative)
        orphans = tuple(_exact_int(row) for row in raw_orphans.tolist())
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("tet primal-conformity kernel returned an invalid result") from exc

    valid_duplicate_groups = all(
        len(key) == 4
        and tuple(sorted(key)) == key
        and len(owners) > 1
        and tuple(sorted(owners)) == owners
        and len(set(owners)) == len(owners)
        and all(0 <= owner < n_tets for owner in owners)
        for key, owners in duplicates
    )
    valid_nonmanifold_groups = all(
        len(key) == 3
        and tuple(sorted(key)) == key
        and len(owners) > 2
        and tuple(sorted(owners)) == owners
        and len(set(owners)) == len(owners)
        and all(0 <= owner < n_tets for owner in owners)
        for key, owners in nonmanifold
    )
    valid_negative_rows = (
        tuple(sorted(negative)) == negative
        and len(set(negative)) == len(negative)
        and all(0 <= row < n_tets for row in negative)
    )
    valid_orphan_rows = (
        tuple(sorted(orphans)) == orphans
        and len(set(orphans)) == len(orphans)
        and all(0 <= row < n_points for row in orphans)
    )
    if not (
        valid_duplicate_groups
        and valid_nonmanifold_groups
        and valid_negative_rows
        and valid_orphan_rows
        and tuple(sorted(duplicates)) == duplicates
        and tuple(sorted(nonmanifold)) == nonmanifold
    ):
        raise RuntimeError("tet primal-conformity kernel returned an invalid result")
    return TetPrimalConformityAudit(duplicates, nonmanifold, negative, orphans)


def _audit_tet_primal_conformity(
    points: np.ndarray,
    tets: np.ndarray,
) -> TetPrimalConformityAudit:
    """Use the strict C++23 audit when possible, otherwise the Python oracle."""
    from core.utils.native_extensions import load_native_polymesh

    native = load_native_polymesh()
    native_compatible = (
        points.dtype == np.dtype(np.float64)
        and tets.dtype == np.dtype(np.int64)
        and points.flags.c_contiguous
        and tets.flags.c_contiguous
    )
    if native is not None and hasattr(native, "audit_tet_primal_conformity") and native_compatible:
        result = native.audit_tet_primal_conformity(points, tets)
    else:
        result = _audit_tet_primal_conformity_python(points, tets)
        return result
    return _normalise_tet_primal_conformity_audit(
        result,
        n_points=int(points.shape[0]),
        n_tets=int(tets.shape[0]),
    )


def _preflight_tet_dual_inputs(
    vertices: Any,
    tetrahedra: Any,
) -> tuple[np.ndarray | None, np.ndarray | None, str | None]:
    """Decode a finite, non-lossy tetrahedral input before any output write.

    ``tet_to_poly_dual`` is also called directly by the layer-transition path,
    so this boundary must not rely on upstream native-tet validation.  In
    particular, ``np.asarray(..., dtype=np.int64)`` would silently truncate
    fractional connectivity and turn negative indices into NumPy reverse
    indexing.  Keep the accepted ordinary integer-array/list inputs unchanged,
    but return an explicit, deterministic refusal for malformed raw data.
    """
    try:
        raw_vertices = np.asarray(vertices)
    except (TypeError, ValueError):
        return None, None, "vertices must be a finite (Nv, 3) array"
    if (
        raw_vertices.ndim != 2
        or raw_vertices.shape[1:] != (3,)
        or raw_vertices.shape[0] == 0
        or np.iscomplexobj(raw_vertices)
    ):
        return None, None, "vertices must be a finite (Nv, 3) array"
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            vertex_array = np.asarray(raw_vertices, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return None, None, "vertices must be a finite (Nv, 3) array"
    if not np.isfinite(vertex_array).all():
        return None, None, "vertices must be a finite (Nv, 3) array"

    try:
        raw_tets = np.asarray(tetrahedra)
    except (TypeError, ValueError):
        return None, None, "tet connectivity must be a non-empty (Nt, 4) array"
    if raw_tets.ndim != 2 or raw_tets.shape[1:] != (4,) or raw_tets.shape[0] == 0:
        return None, None, "tet connectivity must be a non-empty (Nt, 4) array"

    if np.issubdtype(raw_tets.dtype, np.bool_):
        return None, None, "tet connectivity must use non-boolean integer indices"
    if np.issubdtype(raw_tets.dtype, np.integer):
        # Check range before narrowing an unsigned or platform-width dtype.
        if np.any(raw_tets < 0) or np.any(raw_tets >= vertex_array.shape[0]):
            return None, None, "tet connectivity contains an out-of-range vertex index"
        tet_array = np.asarray(raw_tets, dtype=np.int64)
    elif raw_tets.dtype == object:
        raw_values = raw_tets.reshape(-1).tolist()
        if any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral)
            for value in raw_values
        ):
            return None, None, "tet connectivity must use non-boolean integer indices"
        decoded = [int(value) for value in raw_values]
        if any(value < 0 or value >= vertex_array.shape[0] for value in decoded):
            return None, None, "tet connectivity contains an out-of-range vertex index"
        tet_array = np.asarray(decoded, dtype=np.int64).reshape(raw_tets.shape)
    else:
        return None, None, "tet connectivity must use non-boolean integer indices"

    duplicate_rows = np.flatnonzero(
        np.any(np.diff(np.sort(tet_array, axis=1), axis=1) == 0, axis=1)
    )
    if duplicate_rows.size:
        return (
            None,
            None,
            "tet connectivity repeats a vertex index in rows: "
            f"{tuple(int(row) for row in duplicate_rows.tolist())}",
        )

    tet_points = vertex_array[tet_array]
    signed_volume6 = np.einsum(
        "ij,ij->i",
        tet_points[:, 1] - tet_points[:, 0],
        np.cross(tet_points[:, 2] - tet_points[:, 0], tet_points[:, 3] - tet_points[:, 0]),
    )
    nonfinite_volume_rows = np.flatnonzero(~np.isfinite(signed_volume6))
    if nonfinite_volume_rows.size:
        return (
            None,
            None,
            "tet geometry has a non-finite signed volume in rows: "
            f"{tuple(int(row) for row in nonfinite_volume_rows.tolist())}",
        )
    zero_volume_rows = np.flatnonzero(signed_volume6 == 0.0)
    if zero_volume_rows.size:
        return (
            None,
            None,
            "tet geometry is degenerate in rows: "
            f"{tuple(int(row) for row in zero_volume_rows.tolist())}",
        )

    conformity = _audit_tet_primal_conformity(vertex_array, tet_array)
    if conformity.duplicate_tet_groups:
        return (
            None,
            None,
            "tet connectivity contains duplicate canonical tetrahedra: "
            f"{conformity.duplicate_tet_groups}",
        )
    if conformity.nonmanifold_face_groups:
        return (
            None,
            None,
            "tet connectivity has faces with more than two incident tetrahedra: "
            f"{conformity.nonmanifold_face_groups}",
        )
    if conformity.orphan_vertex_rows:
        return (
            None,
            None,
            "tet point array contains vertices with zero tetrahedron incidence: "
            f"{conformity.orphan_vertex_rows}",
        )
    if conformity.negative_orientation_rows:
        log.info(
            "native_poly_primal_orientation_census",
            negative_rows=conformity.negative_orientation_rows,
            hard_reject=False,
        )

    return vertex_array, tet_array, None


def _normalise_entity_label(label: Any) -> tuple[str, str]:
    """Convert a primal boundary-entity label to an OpenFOAM patch label.

    Garimella's construction classifies primal boundary faces before the dual
    subcomplex is assembled.  The polyMesh writer has two semantic fields for
    that classification (patch name and patch type), so accept the compact
    string/tuple forms as well as a mapping for callers that also carry an
    application-specific ``entity`` field.
    """
    if isinstance(label, Mapping):
        name = label.get("patch") or label.get("name") or label.get("label")
        patch_type = label.get("type") or "wall"
    elif isinstance(label, (tuple, list)):
        name = label[0] if label else None
        patch_type = label[1] if len(label) > 1 else "wall"
    else:
        name = label
        patch_type = "wall"
    return str(name or "defaultWall"), str(patch_type or "wall")


def _boundary_entity_labels(
    boundary_faces: Sequence[tuple[int, int, int]],
    vertices: np.ndarray,
    labels: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None,
    classifier: Callable[[tuple[int, int, int], np.ndarray], Any] | None,
) -> dict[tuple[int, int, int], tuple[str, str]]:
    """Resolve source labels for canonical primal boundary triangles."""
    if labels is not None and classifier is not None:
        raise ValueError("boundary_face_labels and boundary_face_classifier are mutually exclusive")

    if classifier is not None:
        return {tri: _normalise_entity_label(classifier(tri, vertices)) for tri in boundary_faces}

    if labels is None:
        return {}

    if isinstance(labels, Mapping):
        canonical_labels = {
            tuple(sorted(map(int, key))): value
            for key, value in labels.items()
            if isinstance(key, (tuple, list)) and len(key) == 3
        }
        resolved: dict[tuple[int, int, int], tuple[str, str]] = {}
        for tri in boundary_faces:
            raw = canonical_labels.get(tuple(sorted(tri)))
            resolved[tri] = _normalise_entity_label(raw)
        return resolved

    if len(labels) != len(boundary_faces):
        raise ValueError(
            "boundary_face_labels sequence must align with the extracted "
            f"boundary faces ({len(boundary_faces)} expected, {len(labels)} received)"
        )
    return {tri: _normalise_entity_label(raw) for tri, raw in zip(boundary_faces, labels)}


def _group_classified_boundary_faces(
    faces: list[list[int]],
    owners: list[int],
    labels: list[tuple[str, str]],
    n_internal: int,
) -> tuple[list[list[int]], list[int], list[dict[str, Any]]]:
    """Make classified boundary faces contiguous and emit boundary entries."""
    groups: dict[tuple[str, str], list[int]] = {}
    for rel_idx, label in enumerate(labels):
        groups.setdefault(label, []).append(rel_idx)

    grouped_faces: list[list[int]] = []
    grouped_owners: list[int] = []
    entries: list[dict[str, Any]] = []
    cursor = n_internal
    for (name, patch_type), rel_indices in groups.items():
        start = cursor
        grouped_faces.extend(faces[rel_idx] for rel_idx in rel_indices)
        grouped_owners.extend(owners[rel_idx] for rel_idx in rel_indices)
        cursor += len(rel_indices)
        entries.append(
            {
                "name": name,
                "type": patch_type,
                "nFaces": len(rel_indices),
                "startFace": start,
            }
        )
    return grouped_faces, grouped_owners, entries


def _ordered_boundary_labels(
    labels: list[tuple[str, str]], owners: list[int]
) -> list[tuple[str, str]]:
    """Apply the same stable owner ordering used by ``_order_and_concat``."""
    order = sorted(range(len(labels)), key=lambda idx: owners[idx])
    return [labels[idx] for idx in order]


def _star_validity(
    points: np.ndarray,
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    n_cells: int,
    *,
    tolerance: float = 1e-12,
    max_examples: int = 8,
) -> tuple[int, int, tuple[dict[str, Any], ...]]:
    """Check Garimella's signed face-edge-region subtet decomposition.

    A face is oriented outward from its owner.  The neighbour sees the same
    face in reverse.  For an outward face, ``-det(edge, face_center, region_center)``
    must be positive for every face edge.  The arithmetic mean of the dual
    vertices is the fast-path witness.  Only when it fails, eight deterministic
    half-space projection sweeps seek another kernel witness; the original
    signed-subtet inequalities are then rechecked without relaxing ``tolerance``.
    """
    if not points.size or not faces or not owner:
        return 0, 0, ()

    from core.utils.native_extensions import load_native_polymesh

    native = load_native_polymesh()
    if native is not None and hasattr(native, "star_validity"):
        return native.star_validity(
            points,
            faces,
            owner,
            neighbour,
            n_cells,
            tolerance,
            max_examples,
        )

    cell_faces: list[list[tuple[list[int], int]]] = [[] for _ in range(n_cells)]
    n_internal = len(neighbour)
    for face_id, face in enumerate(faces):
        owner_id = int(owner[face_id])
        if 0 <= owner_id < n_cells:
            cell_faces[owner_id].append((list(face), face_id))
        if face_id < n_internal:
            neighbour_id = int(neighbour[face_id])
            if 0 <= neighbour_id < n_cells:
                cell_faces[neighbour_id].append((list(reversed(face)), face_id))

    scale = max(
        float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) ** 3,
        1e-30,
    )
    invalid_cells = 0
    invalid_subtets = 0
    examples: list[dict[str, Any]] = []
    for cell_id, cell_face_refs in enumerate(cell_faces):
        cell_vertex_ids = sorted({vertex for face, _ in cell_face_refs for vertex in face})
        if len(cell_vertex_ids) < 4:
            invalid_cells += 1
            invalid_subtets += 1
            if len(examples) < max_examples:
                examples.append(
                    {
                        "cell": cell_id,
                        "face": None,
                        "edge": None,
                        "normalized_signed_volume6": 0.0,
                        "reason": "fewer_than_four_dual_vertices",
                    }
                )
            continue

        region_center = points[np.asarray(cell_vertex_ids)].mean(axis=0)

        def audit_center(*, collect_examples: bool) -> int:
            violations = 0
            for face, face_id in cell_face_refs:
                face_center = points[np.asarray(face)].mean(axis=0)
                for edge_index, (a, b) in enumerate(zip(face, face[1:] + face[:1], strict=True)):
                    signed_volume6 = float(
                        np.dot(
                            points[b] - points[a],
                            np.cross(
                                face_center - points[a],
                                region_center - points[a],
                            ),
                        )
                    )
                    normalized = -signed_volume6 / scale
                    if normalized <= tolerance:
                        violations += 1
                        if collect_examples and len(examples) < max_examples:
                            examples.append(
                                {
                                    "cell": cell_id,
                                    "face": face_id,
                                    "edge": (int(a), int(b)),
                                    "edge_index": edge_index,
                                    "signed_volume6": signed_volume6,
                                    "normalized_signed_volume6": normalized,
                                }
                            )
            return violations

        cell_bad_count = audit_center(collect_examples=False)
        if cell_bad_count and np.all(np.isfinite(region_center)) and np.isfinite(scale):
            tolerance_scaled = tolerance * scale
            inward_guard = (
                64.0
                * float(np.finfo(np.float64).eps)
                * max(
                    scale,
                    abs(tolerance_scaled),
                    float(np.finfo(np.float64).tiny),
                )
            )
            for _sweep in range(8):
                projection_valid = True
                for face, _face_id in cell_face_refs:
                    face_center = points[np.asarray(face)].mean(axis=0)
                    for a, b in zip(face, face[1:] + face[:1], strict=True):
                        edge = points[b] - points[a]
                        face_offset = face_center - points[a]
                        normal = np.cross(edge, face_offset)
                        signed_volume6 = float(np.dot(normal, region_center - points[a]))
                        normal_squared = float(np.dot(normal, normal))
                        if not (
                            np.isfinite(signed_volume6)
                            and np.isfinite(normal_squared)
                            and normal_squared > float(np.finfo(np.float64).tiny)
                        ):
                            projection_valid = False
                            continue
                        if signed_volume6 >= -tolerance_scaled:
                            region_center -= (
                                (signed_volume6 + tolerance_scaled + inward_guard) / normal_squared
                            ) * normal
                if not projection_valid:
                    break
                cell_bad_count = audit_center(collect_examples=False)
                if cell_bad_count == 0:
                    break

        cell_bad_count = audit_center(collect_examples=True)
        cell_bad = cell_bad_count > 0
        invalid_subtets += cell_bad_count
        if cell_bad:
            invalid_cells += 1
    return invalid_cells, invalid_subtets, tuple(examples)


# ---------------------------------------------------------------------------
# Tet topology helpers
# ---------------------------------------------------------------------------

# tet 의 4 face (각 3 vertex), outward winding (v0,v1,v2,v3) 에서 normal 이
# cell 바깥 방향을 향하도록. OpenFOAM tet winding 과 동일한 규칙.
_TET_FACES: tuple[tuple[int, int, int], ...] = (
    (1, 2, 3),  # opposite v0
    (0, 3, 2),  # opposite v1
    (0, 1, 3),  # opposite v2
    (0, 2, 1),  # opposite v3
)

# tet 의 6 edges (정점 pair, sorted)
_TET_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (0, 3),
    (1, 2),
    (1, 3),
    (2, 3),
)


def _compute_tet_dual_points_python(
    V: np.ndarray,
    T: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Python oracle for Garimella dual points and placement provenance.

    A well-centered tetrahedron uses its circumcenter.  Otherwise the point is
    placed on the centroid-to-circumcenter segment at the closest parameter
    that remains inside the tetrahedron.  The centroid is the robust fallback
    for singular or non-finite circumcenter systems.

    Status values match the native ABI: 0=circumcenter, 1=clipped,
    2=singular-centroid, 3=non-finite-solve-centroid.
    """
    dual_points = np.empty((T.shape[0], 3), dtype=np.float64)
    statuses = np.empty(T.shape[0], dtype=np.uint8)
    for ti, tet in enumerate(T):
        p = V[tet]
        centroid = p.mean(axis=0)
        try:
            matrix = 2.0 * np.stack([p[i] - p[0] for i in (1, 2, 3)])
            rhs = np.asarray(
                [np.dot(p[i], p[i]) - np.dot(p[0], p[0]) for i in (1, 2, 3)],
                dtype=np.float64,
            )
            circumcenter = np.linalg.solve(matrix, rhs)
            edge_matrix = np.column_stack([p[i] - p[0] for i in (1, 2, 3)])
            bary_tail = np.linalg.solve(edge_matrix, circumcenter - p[0])
            bary = np.asarray([1.0 - bary_tail.sum(), *bary_tail], dtype=np.float64)
        except np.linalg.LinAlgError:
            dual_points[ti] = centroid
            statuses[ti] = 2
            continue

        if not np.isfinite(circumcenter).all() or not np.isfinite(bary).all():
            dual_points[ti] = centroid
            statuses[ti] = 3
            continue

        alpha = 1.0
        for bary_c in bary:
            if bary_c < 0.0:
                alpha = min(alpha, 0.25 / (0.25 - float(bary_c)))
        if alpha < 1.0:
            # Stay strictly inside after clipping to a boundary face.  This
            # avoids manufacturing a zero signed subtet from the dual point.
            alpha = max(0.0, alpha * (1.0 - 1e-12))
        result = centroid + alpha * (circumcenter - centroid)
        if not np.isfinite(result).all():
            dual_points[ti] = centroid
            statuses[ti] = 3
            continue
        dual_points[ti] = result
        statuses[ti] = 1 if alpha < 1.0 else 0
    return dual_points, statuses


def _compute_tet_dual_points_with_status(
    V: np.ndarray,
    T: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Use the strict contiguous C++23 kernel, or the Python oracle."""
    from core.utils.native_extensions import load_native_polymesh

    if V.ndim != 2 or V.shape[1:] != (3,):
        raise ValueError("points must have shape (N, 3)")
    if T.ndim != 2 or T.shape[1:] != (4,):
        raise ValueError("tets must have shape (M, 4)")
    try:
        finite_points = bool(np.isfinite(V).all())
    except TypeError as exc:
        raise ValueError("points must contain only finite coordinates") from exc
    if not finite_points:
        raise ValueError("points must contain only finite coordinates")
    if np.issubdtype(T.dtype, np.bool_) or not np.issubdtype(T.dtype, np.integer):
        raise ValueError("tets must contain integer vertex indices")
    if T.size:
        if np.any(T < 0) or np.any(T >= V.shape[0]):
            raise ValueError("tet vertex index out of range")
        if np.any(np.diff(np.sort(T, axis=1), axis=1) == 0):
            raise ValueError("tet repeats a vertex index")

    native = load_native_polymesh()
    native_compatible = (
        V.dtype == np.dtype(np.float64)
        and T.dtype == np.dtype(np.int64)
        and V.flags.c_contiguous
        and T.flags.c_contiguous
    )
    if native is not None and hasattr(native, "compute_tet_dual_points") and native_compatible:
        result = native.compute_tet_dual_points(V, T)
    else:
        result = _compute_tet_dual_points_python(V, T)

    points_array = np.asarray(result[0])
    status_array = np.asarray(result[1])
    if (
        points_array.dtype != np.dtype(np.float64)
        or points_array.shape != (T.shape[0], 3)
        or status_array.dtype != np.dtype(np.uint8)
        or status_array.shape != (T.shape[0],)
        or not np.isfinite(points_array).all()
        or np.any(status_array > 3)
    ):
        raise RuntimeError("tet dual-point kernel returned an invalid result")
    return points_array, status_array


def _compute_tet_dual_points(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Place Garimella dual points without changing the public ndarray API."""
    return _compute_tet_dual_points_with_status(V, T)[0]


def _build_tet_topology(
    T: np.ndarray,
    n_verts: int,
) -> tuple[
    dict[int, list[int]],  # vertex → list of tet indices
    dict[tuple[int, int], list[int]],  # edge (sorted) → list of tet indices
    dict[tuple[int, int, int], list[int]],  # face (sorted triple) → list of tet indices
]:
    """Build ordered tet incidence maps through C++23, with NumPy fallback."""
    from core.utils.native_extensions import load_native_polymesh

    native = load_native_polymesh()
    if native is not None and hasattr(native, "build_tet_incidence_maps"):
        return native.build_tet_incidence_maps(T, int(n_verts))

    vert_tets: dict[int, list[int]] = defaultdict(list)
    edge_tets: dict[tuple[int, int], list[int]] = defaultdict(list)
    face_tets: dict[tuple[int, int, int], list[int]] = defaultdict(list)

    n_tets = T.shape[0]
    ti_arr = np.arange(n_tets, dtype=np.int64)

    # --- vertex → tet (4 verts per tet) ---
    # T shape: (n_tets, 4); repeat ti for each of the 4 verts
    vert_col = T.reshape(-1)  # (n_tets*4,)
    ti_col = np.repeat(ti_arr, 4)  # (n_tets*4,)
    for v, ti in zip(vert_col.tolist(), ti_col.tolist()):
        vert_tets[v].append(ti)

    # --- edge → tet (6 edges per tet, fixed indices _TET_EDGES) ---
    _EA = np.array([a for a, _ in _TET_EDGES], dtype=np.int64)  # (6,)
    _EB = np.array([b for _, b in _TET_EDGES], dtype=np.int64)  # (6,)
    # for each tet gather the two endpoint global indices
    ea = T[:, _EA]  # (n_tets, 6)
    eb = T[:, _EB]  # (n_tets, 6)
    emin = np.minimum(ea, eb)  # (n_tets, 6)
    emax = np.maximum(ea, eb)  # (n_tets, 6)
    ti_e = np.repeat(ti_arr, 6)  # (n_tets*6,)
    for (a, b), ti in zip(zip(emin.reshape(-1).tolist(), emax.reshape(-1).tolist()), ti_e.tolist()):
        edge_tets[(a, b)].append(ti)

    # --- face → tet (4 faces per tet, fixed indices _TET_FACES) ---
    _FA = np.array([tri[0] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    _FB = np.array([tri[1] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    _FC = np.array([tri[2] for tri in _TET_FACES], dtype=np.int64)  # (4,)
    fa = T[:, _FA]  # (n_tets, 4)
    fb = T[:, _FB]  # (n_tets, 4)
    fc = T[:, _FC]  # (n_tets, 4)
    # stack and sort each row of 3 to get canonical key
    face_verts = np.stack([fa, fb, fc], axis=2)  # (n_tets, 4, 3)
    face_verts_sorted = np.sort(face_verts, axis=2)  # (n_tets, 4, 3)
    ti_f = np.repeat(ti_arr, 4)  # (n_tets*4,)
    fv = face_verts_sorted.reshape(-1, 3)  # (n_tets*4, 3)
    for row, ti in zip(fv.tolist(), ti_f.tolist()):
        face_tets[(row[0], row[1], row[2])].append(ti)

    return vert_tets, edge_tets, face_tets


def _extract_boundary(
    face_tets: dict[tuple[int, int, int], list[int]],
) -> list[tuple[int, int, int]]:
    """단 1 tet 만 공유하는 triangle = boundary face."""
    return [k for k, tl in face_tets.items() if len(tl) == 1]


def _tet_faces_with_edge(tv: np.ndarray, a: int, b: int) -> list[tuple[int, int, int]]:
    """tet 정점 tv 중 edge(a,b) 를 포함하는 2개 face(정렬된 triple)."""
    out: list[tuple[int, int, int]] = []
    for face in _TET_FACES:
        tri = (int(tv[face[0]]), int(tv[face[1]]), int(tv[face[2]]))
        if a in tri and b in tri:
            out.append(tuple(sorted(tri)))
    return out


def _ordered_tet_ring(
    e: tuple[int, int],
    edge_tets: dict[tuple[int, int], list[int]],
    face_tets: dict[tuple[int, int, int], list[int]],
    T: np.ndarray,
) -> tuple[list[int], bool]:
    """edge e 를 공유하는 tet 들을 공유 face 로 walk 하여 정렬된 ring 반환.

    내부 edge(주변 face 가 모두 2-tet 공유) -> 닫힌 ring, closed=True.
    경계 edge(끝 face 가 1-tet, boundary face) -> open fan, closed=False.
    """
    a, b = e
    tets = edge_tets.get(e, [])
    if not tets:
        return [], False
    tet_faces = {ti: _tet_faces_with_edge(T[ti], a, b) for ti in tets}
    start, start_face = tets[0], tet_faces[tets[0]][0]
    for ti in tets:
        for f in tet_faces[ti]:
            if len(face_tets[f]) == 1:
                start, start_face = ti, f
                break
        else:
            continue
        break
    ring = [start]
    visited = {start}
    cur, cur_face = start, start_face
    while True:
        f0, f1 = tet_faces[cur]
        other = f1 if f0 == cur_face else f0
        nbrs = face_tets[other]
        if len(nbrs) < 2:
            return ring, False
        nxt = nbrs[1] if nbrs[0] == cur else nbrs[0]
        if nxt in visited:
            return ring, True
        ring.append(nxt)
        visited.add(nxt)
        cur, cur_face = nxt, other


def _vertex_fan_components(
    v_in: int,
    tets: Sequence[int],
    T: np.ndarray,
) -> list[list[int]]:
    """Partition the tets incident to primal vertex ``v_in`` into face-connected
    "fan" components.

    Two tets that both touch ``v_in`` are adjacent iff they share one of the
    three tet faces incident to ``v_in`` (the face opposite ``v_in`` does not
    count -- it never touches ``v_in``).  For an ordinary manifold vertex this
    always yields a single component (one closed or open fan).  A
    non-manifold vertex -- e.g. two tets meeting only along an edge through
    ``v_in``, never sharing a face -- yields >1 component.

    Forcing such a vertex into a single dual cell silently drops whichever
    tets the ring-walk in ``_ordered_tet_ring``/``_dual_cell_verts`` never
    reaches (GAP: non-manifold-fan dual cell).  The caller must instead build
    one dual cell per returned component.
    """
    if not tets:
        return []
    face_owners: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for ti in tets:
        tv = T[ti]
        for face in _TET_FACES:
            tri = tuple(sorted((int(tv[face[0]]), int(tv[face[1]]), int(tv[face[2]]))))
            if v_in in tri:
                face_owners[tri].append(ti)

    adjacency: dict[int, set[int]] = defaultdict(set)
    for owners in face_owners.values():
        for i in range(len(owners)):
            for j in range(i + 1, len(owners)):
                a, b = owners[i], owners[j]
                if a == b:
                    continue
                adjacency[a].add(b)
                adjacency[b].add(a)

    visited: set[int] = set()
    components: list[list[int]] = []
    for ti in tets:
        if ti in visited:
            continue
        stack = [ti]
        visited.add(ti)
        comp: list[int] = []
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adjacency.get(cur, ()):
                if nb not in visited:
                    visited.add(nb)
                    stack.append(nb)
        components.append(sorted(comp))
    return components


def _surface_planes(
    V: np.ndarray,
    boundary_faces: list[tuple[int, int, int]],
) -> list[tuple[np.ndarray, float]]:
    """원본 입력 surface triangle 들의 고유 평면(normal, offset) 목록."""
    planes: list[tuple[np.ndarray, float]] = []
    seen: set[tuple[int, ...]] = set()
    for tri in boundary_faces:
        p0, p1, p2 = V[tri[0]], V[tri[1]], V[tri[2]]
        n = np.cross(p1 - p0, p2 - p0)
        norm = float(np.linalg.norm(n))
        if norm < 1e-12:
            continue
        n = n / norm
        d = -float(np.dot(n, p0))
        key = tuple(np.round(np.append(n, d) * 1e4).astype(np.int64).tolist())
        key = min(key, tuple(-x for x in key))
        if key in seen:
            continue
        seen.add(key)
        planes.append((n, d))
    return planes


def _area_split(
    points: np.ndarray,
    faces: list[list[int]],
    planes: list[tuple[np.ndarray, float]],
    tol: float = 1e-6,
) -> tuple[float, float]:
    """boundary face 들을 (원본 surface 평면 위 area, 그 외 area) 로 분리."""
    from core.utils.native_extensions import load_native_polymesh

    native = load_native_polymesh()
    if native is not None and hasattr(native, "face_plane_geometry"):
        plane_normals = np.asarray([normal for normal, _ in planes], dtype=np.float64).reshape(
            -1, 3
        )
        plane_offsets = np.asarray([offset for _, offset in planes], dtype=np.float64)
        on, off, _ = native.face_plane_geometry(
            points,
            faces,
            plane_normals,
            plane_offsets,
            float(tol),
        )
        return float(on), float(off)

    if not planes:
        off = 0.0
        for f in faces:
            p = points[np.asarray(f, dtype=int)]
            acc = np.zeros(3)
            for i in range(1, len(f) - 1):
                acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
            off += float(np.linalg.norm(acc))
        return 0.0, off
    plane_normals = np.asarray([normal for normal, _ in planes], dtype=np.float64)
    plane_offsets = np.asarray([offset for _, offset in planes], dtype=np.float64)
    on = off = 0.0
    for f in faces:
        p = points[np.asarray(f, dtype=int)]
        acc = np.zeros(3)
        for i in range(1, len(f) - 1):
            acc = acc + np.cross(p[i] - p[0], p[i + 1] - p[0]) / 2.0
        area = float(np.linalg.norm(acc))
        signed_distances = p @ plane_normals.T + plane_offsets
        is_on = bool(np.any(np.all(np.abs(signed_distances) < tol, axis=0)))
        if is_on:
            on += area
        else:
            off += area
    return on, off


def _order_and_concat(
    i_faces: list[list[int]],
    i_own: list[int],
    i_nbr: list[int],
    b_faces: list[list[int]],
    b_own: list[int],
) -> tuple[list[list[int]], list[int], list[int], int]:
    """internal(owner,nbr 정렬) + boundary(owner 정렬) face 를 하나로 합친다."""
    oi = sorted(range(len(i_faces)), key=lambda k: (i_own[k], i_nbr[k]))
    ob = sorted(range(len(b_faces)), key=lambda k: b_own[k])
    faces = [i_faces[k] for k in oi] + [b_faces[k] for k in ob]
    owner = [i_own[k] for k in oi] + [b_own[k] for k in ob]
    nbr = [i_nbr[k] for k in oi]
    return faces, owner, nbr, len(b_faces)


# ---------------------------------------------------------------------------
# Dual cell 생성
# ---------------------------------------------------------------------------


def _unique_row_ids(pts: np.ndarray, tol: float = 1e-9) -> np.ndarray:
    """좌표 양자화 기반 unique row index (dedup 후 inverse)."""
    if pts.size == 0:
        return np.zeros(0, dtype=np.int64)
    scale = 1.0 / max(tol, 1e-30)
    keys = np.round(pts * scale).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    return np.asarray(inverse, dtype=np.int64).reshape(-1)


def _dual_cell_verts(
    v_in: int,
    V: np.ndarray,
    tet_ids: Sequence[int],
    tet_dual_points: np.ndarray,
    is_boundary_component: bool,
    boundary_tris: Sequence[tuple[int, int, int]],
    boundary_edges: Sequence[tuple[int, int]],
) -> np.ndarray:
    """input vertex v_in 의 (단일 fan 컴포넌트) dual cell 을 이루는 3D vertex 집합.

    ``tet_ids``/``boundary_tris``/``boundary_edges`` 는 이미 하나의
    ``_vertex_fan_components`` 컴포넌트로 국한된 목록이어야 한다 -- 이래야
    non-manifold vertex (여러 개의 서로 분리된 fan) 를 하나의 dual cell 로
    뭉개지 않고, 컴포넌트마다 별도의 cell 을 만들 수 있다.

    - internal component: tet dual point 만
    - boundary component: tet dual point + boundary face centroid +
      boundary edge midpoint + v 자체 (surface 에 남는다)
    """
    pts = list(tet_dual_points[np.asarray(tet_ids, dtype=np.int64)]) if len(tet_ids) else []
    if is_boundary_component:
        # boundary face centroids (v_in 포함, 이 컴포넌트 소속만)
        for tri in boundary_tris:
            pts.append(V[list(tri)].mean(axis=0))
        # boundary edge midpoints (v_in 포함, 이 컴포넌트 소속만)
        for a, b in boundary_edges:
            pts.append(0.5 * (V[a] + V[b]))
        # vertex 자신
        pts.append(V[v_in])
    return np.asarray(pts, dtype=np.float64) if pts else np.zeros((0, 3))


def _smooth_interior_tet_verts(
    V: np.ndarray,
    T: np.ndarray,
    is_boundary_vert: np.ndarray,
    edge_tets: dict[tuple[int, int], list[int]],
    n_iter: int = 10,
    relax: float = 0.5,
) -> np.ndarray:
    """interior tet vertex 만 Laplacian smoothing (boundary vertex 는 고정).

    per-vertex inversion 가드: 이동 후 incident tet vol 이 하나라도
    ``<= 1e-4*orig_vol`` 이면 그 vertex 이동만 revert. 전역적으로
    min_tet_vol <= 0 이 남으면 전체 V 를 원본으로 revert.
    """

    def _tet_vols(Vc: np.ndarray, idx: np.ndarray) -> np.ndarray:
        tv = T[idx]
        p0, p1, p2, p3 = Vc[tv[:, 0]], Vc[tv[:, 1]], Vc[tv[:, 2]], Vc[tv[:, 3]]
        return np.einsum("ij,ij->i", p1 - p0, np.cross(p2 - p0, p3 - p0)) / 6.0

    V0 = V.copy()
    orig_vol = np.abs(_tet_vols(V0, np.arange(T.shape[0])))
    nbrs: dict[int, set[int]] = defaultdict(set)
    vert_tets: dict[int, list[int]] = defaultdict(list)
    for a, b in edge_tets:
        nbrs[a].add(b)
        nbrs[b].add(a)
    for ti, tv in enumerate(T):
        for v in tv:
            vert_tets[int(v)].append(ti)
    interior = [v for v in range(V.shape[0]) if not is_boundary_vert[v] and nbrs.get(v)]

    Vs = V0.copy()
    for _ in range(n_iter):
        for v in interior:
            nb = np.array(list(nbrs[v]), dtype=np.int64)
            old = Vs[v].copy()
            Vs[v] = old + relax * (Vs[nb].mean(axis=0) - old)
            idx = np.asarray(vert_tets[v], dtype=np.int64)
            if np.any(np.abs(_tet_vols(Vs, idx)) <= 1e-4 * orig_vol[idx]):
                Vs[v] = old

    if np.any(_tet_vols(Vs, np.arange(T.shape[0])) <= 0):
        return V0
    return Vs


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def tet_to_poly_dual(
    V: np.ndarray,
    T: np.ndarray,
    case_dir: Path,
    *,
    min_cell_verts: int = 4,
    boundary_face_labels: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None = None,
    boundary_face_entities: Mapping[tuple[int, int, int], Any] | Sequence[Any] | None = None,
    boundary_face_classifier: Callable[[tuple[int, int, int], np.ndarray], Any] | None = None,
    _dual_point_mode: str = "garimella",
) -> PolyDualResult:
    """tet mesh (V, T) 를 polyhedral dual 로 변환 후 OpenFOAM polyMesh 로 저장.

    Args:
        V: (Nv, 3) tet mesh points.
        T: (Nt, 4) tet cell connectivity (zero-based).
        case_dir: 출력 OpenFOAM case 디렉터리.
        min_cell_verts: dual cell 을 생성하기 위한 최소 vertex 수. 4 이상이어야
            ConvexHull 이 3D polyhedron 을 만들 수 있다.
        boundary_face_labels: optional source patch/entity labels keyed by canonical
            primal boundary triangle or supplied in extracted-boundary order.
        boundary_face_entities: alias for ``boundary_face_labels`` for callers that
            name the Garimella classification explicitly.
        boundary_face_classifier: optional callback receiving ``(triangle, V)`` and
            returning a patch name, ``(name, type)`` pair, or mapping.

    Returns:
        PolyDualResult.
    """
    t0 = time.perf_counter()

    vertex_array, tet_array, preflight_error = _preflight_tet_dual_inputs(V, T)
    if preflight_error is not None:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message=f"invalid tet dual input: {preflight_error}",
        )
    assert vertex_array is not None
    assert tet_array is not None
    V = vertex_array
    T = tet_array
    original_V = V.copy()
    n_verts = int(V.shape[0])
    n_tets = int(T.shape[0])

    try:
        from scipy.spatial import ConvexHull  # noqa: PLC0415
    except Exception as exc:
        return PolyDualResult(False, 0.0, message=f"scipy 필요: {exc}")

    # 1) topology
    vert_tets, edge_tets, face_tets = _build_tet_topology(T, n_verts)
    boundary_faces = _extract_boundary(face_tets)
    if boundary_face_labels is not None and boundary_face_entities is not None:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message="boundary_face_labels and boundary_face_entities are mutually exclusive",
        )
    supplied_entity_labels = (
        boundary_face_labels if boundary_face_labels is not None else boundary_face_entities
    )
    try:
        if isinstance(supplied_entity_labels, Mapping):
            mapped_triangles = {
                tuple(sorted(map(int, key)))
                for key in supplied_entity_labels
                if isinstance(key, (tuple, list)) and len(key) == 3
            }
            missing = tuple(sorted(set(boundary_faces).difference(mapped_triangles)))
            if missing:
                mapping_name = (
                    "boundary_face_labels"
                    if boundary_face_labels is not None
                    else "boundary_face_entities"
                )
                raise ValueError(
                    f"{mapping_name} must cover every extracted boundary triangle; "
                    f"missing canonical triangles: {missing}"
                )
        source_entity_labels = _boundary_entity_labels(
            boundary_faces,
            V,
            supplied_entity_labels,
            boundary_face_classifier,
        )
    except (TypeError, ValueError) as exc:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message=f"boundary entity classification failed: {exc}",
        )
    classification_active = bool(
        supplied_entity_labels is not None or boundary_face_classifier is not None
    )

    # boundary vertex / edge 집합
    is_boundary_vert = np.zeros(n_verts, dtype=bool)
    boundary_edges_set: set[tuple[int, int]] = set()
    boundary_faces_of_vert: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    boundary_edges_of_vert: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for tri in boundary_faces:
        for v in tri:
            is_boundary_vert[v] = True
            boundary_faces_of_vert[v].append(tri)
        # boundary edges = 3 edges of boundary triangle
        e01 = (min(tri[0], tri[1]), max(tri[0], tri[1]))
        e12 = (min(tri[1], tri[2]), max(tri[1], tri[2]))
        e20 = (min(tri[2], tri[0]), max(tri[2], tri[0]))
        for e in (e01, e12, e20):
            boundary_edges_set.add(e)
    for a, b in boundary_edges_set:
        boundary_edges_of_vert[a].append((a, b))
        boundary_edges_of_vert[b].append((a, b))

    V = _smooth_interior_tet_verts(V, T, is_boundary_vert, edge_tets)

    if _dual_point_mode == "centroid":
        tet_dual_points = V[T].mean(axis=1)
    elif _dual_point_mode == "garimella":
        tet_dual_points = (
            _compute_tet_dual_points(V, T) if classification_active else V[T].mean(axis=1)
        )
    else:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message=f"unknown dual point mode: {_dual_point_mode}",
        )

    log.info(
        "native_poly_dual_topology",
        n_verts=n_verts,
        n_tets=n_tets,
        n_boundary_faces=len(boundary_faces),
        n_boundary_verts=int(is_boundary_vert.sum()),
    )

    # 2) 각 input vertex 마다 dual cell 점 집합 + boundary cap 후보(ConvexHull) 생성
    all_points: list[np.ndarray] = []  # unique dual points (나중에 stack)
    cell_face_lists: list[list[list[int]]] = []  # cell_i → [face_vertices, ...]
    cell_face_is_cap: list[list[bool]] = []  # cell_i → face 가 surface cap 인지
    cell_face_labels: list[list[tuple[str, str] | None]] = []
    cell_centroid_list: list[np.ndarray] = []  # cell_i → 3D centroid
    # (input vertex, incident tet id) → cell index.  A non-manifold vertex
    # (>=2 disconnected fan components, see ``_vertex_fan_components``) maps
    # to *multiple* cell indices -- one per component -- so any tet incident
    # to that vertex resolves to the cell of its own component only.
    cell_of_tet_vert: dict[tuple[int, int], int] = {}
    boundary_face_tet: dict[tuple[int, int, int], int] = {
        tri: face_tets[tri][0] for tri in boundary_faces
    }
    # 점 dedup 을 위해 global dict (3D 좌표 → global idx)
    point_id_of: dict[tuple[int, int, int], int] = {}
    point_tol = 1e-9
    scale = 1.0 / point_tol

    def _add_point(p: np.ndarray) -> int:
        key = tuple(np.round(p * scale).astype(np.int64).tolist())
        if key in point_id_of:
            return point_id_of[key]
        idx = len(point_id_of)
        point_id_of[key] = idx
        all_points.append(p)
        return idx

    # tet dual point 는 인접 vertex 들이 공유하므로 미리 고정 등록.
    tet_point_id = np.array(
        [_add_point(tet_dual_points[ti]) for ti in range(n_tets)],
        dtype=np.int64,
    )
    # boundary face centroid / boundary edge midpoint 도 안정적인 dual point id 로
    # 미리 등록한다 (POLY-S3: on-plane cap + boundary-edge separating face 가 공유).
    bface_pid: dict[tuple[int, int, int], int] = {
        tri: _add_point(V[list(tri)].mean(axis=0)) for tri in boundary_faces
    }
    bedge_pid: dict[tuple[int, int], int] = {
        e: _add_point(0.5 * (V[e[0]] + V[e[1]])) for e in boundary_edges_set
    }
    boundary_vertex_pid: dict[int, int] = {}
    if classification_active:
        boundary_vertex_pid = {
            v: _add_point(V[v]) for v in np.flatnonzero(is_boundary_vert).tolist()
        }

    n_skipped = 0
    n_nonmanifold_vertices = 0
    n_fan_split_cells = 0
    for v_in in range(n_verts):
        tets_here = vert_tets.get(v_in, [])
        components = _vertex_fan_components(v_in, tets_here, T)
        if len(components) > 1:
            n_nonmanifold_vertices += 1
            log.info(
                "native_poly_dual_nonmanifold_fan_split",
                vertex=v_in,
                n_components=len(components),
                component_sizes=[len(c) for c in components],
            )

        for comp in components:
            comp_tet_set = set(comp)
            n_tet_pts = len(comp)
            comp_boundary_tris = [
                tri
                for tri in boundary_faces_of_vert.get(v_in, [])
                if boundary_face_tet[tri] in comp_tet_set
            ]
            comp_boundary_edges: list[tuple[int, int]] = []
            seen_edges: set[tuple[int, int]] = set()
            for tri in comp_boundary_tris:
                for other in tri:
                    if other == v_in:
                        continue
                    edge = (min(v_in, other), max(v_in, other))
                    if edge not in seen_edges:
                        seen_edges.add(edge)
                        comp_boundary_edges.append(edge)
            is_boundary_component = bool(comp_boundary_tris)

            pts = _dual_cell_verts(
                v_in,
                V,
                comp,
                tet_dual_points,
                is_boundary_component,
                comp_boundary_tris,
                comp_boundary_edges,
            )
            if pts.shape[0] < min_cell_verts:
                n_skipped += 1
                continue
            # ConvexHull 로 polyhedron 생성
            try:
                # Prefer the exact hull.  ``QJ`` perturbs the input points and
                # can turn an otherwise coplanar dual face into a warped one;
                # retain it only as a recovery path for genuinely degenerate
                # point sets.
                try:
                    hull = ConvexHull(pts)
                except Exception:
                    hull = ConvexHull(pts, qhull_options="QJ")
            except Exception:
                n_skipped += 1
                continue
            # hull.simplices 는 triangle 분할. 평면 coplanar triangle 을 병합해 polygon 생성.
            # hull.equations = (n_simplex, 4) [a, b, c, d] (a·x+b·y+c·z+d=0)
            simplices = hull.simplices
            eqs = hull.equations
            # 같은 face-plane 의 simplex 는 같은 group. 평면 방정식을 정규화해 dedup.
            # rounding 으로 grouping
            eq_key = np.round(eqs * 1e6).astype(np.int64)
            # group by eq_key
            group_of: dict[tuple[int, ...], list[int]] = defaultdict(list)
            for si, k in enumerate(map(tuple, eq_key.tolist())):
                group_of[k].append(si)
            # 각 group 에서 polygon vertex (ordered) 추출
            local_cell_centroid = pts.mean(axis=0)
            cell_face_verts: list[list[int]] = []
            cell_face_caps: list[bool] = []
            cell_face_entity_labels: list[tuple[str, str] | None] = []
            local_face_triangles = {
                n_tet_pts + local_idx: tri for local_idx, tri in enumerate(comp_boundary_tris)
            }
            for _, simp_ids in group_of.items():
                # union 의 vertex 집합
                verts_local: set[int] = set()
                for si in simp_ids:
                    verts_local.update(int(x) for x in simplices[si])
                verts_list = sorted(verts_local)
                if len(verts_list) < 3:
                    continue
                # 평면 위 CCW sort (cell centroid 밖 방향 normal)
                poly_pts = pts[verts_list]
                c = poly_pts.mean(axis=0)
                n_plane = np.array([eqs[simp_ids[0], 0], eqs[simp_ids[0], 1], eqs[simp_ids[0], 2]])
                # ConvexHull 은 normal 을 바깥 방향으로 내보냄 (d < 0 for inside). centroid
                # 에서 c 로 가는 방향이 n_plane 과 같은 부호여야 cell 바깥.
                # e1 = c 에서 첫 vertex 로
                e1 = poly_pts[0] - c
                e1 -= n_plane * float(np.dot(e1, n_plane))
                if float(np.linalg.norm(e1)) < 1e-30:
                    # degenerate — 다른 vertex 로 재시도
                    for k in range(1, len(poly_pts)):
                        e1 = poly_pts[k] - c
                        e1 -= n_plane * float(np.dot(e1, n_plane))
                        if float(np.linalg.norm(e1)) >= 1e-30:
                            break
                n_len = float(np.linalg.norm(e1))
                if n_len < 1e-30:
                    continue
                e1 = e1 / n_len
                e2 = np.cross(n_plane, e1)
                rel = poly_pts - c
                proj = np.stack([rel @ e1, rel @ e2], axis=1)
                angles = np.arctan2(proj[:, 1], proj[:, 0])
                order = np.argsort(angles)
                ordered_verts_local = [verts_list[int(k)] for k in order]
                # global id 매핑
                global_ids = [_add_point(pts[lv]) for lv in ordered_verts_local]
                cell_face_verts.append(global_ids)
                is_cap = any(lv >= n_tet_pts for lv in ordered_verts_local)
                cell_face_caps.append(is_cap)
                cap_triangles = {
                    local_face_triangles[lv]
                    for lv in ordered_verts_local
                    if lv in local_face_triangles
                }
                cap_labels = {
                    source_entity_labels[tri]
                    for tri in cap_triangles
                    if tri in source_entity_labels
                }
                # A hull cap may span multiple coplanar source faces.  The
                # classified path below splits those caps per source triangle; the
                # single fallback label here keeps the old ConvexHull path usable
                # if its monotonic guard rejects the classified topology.
                cell_face_entity_labels.append(
                    next(iter(cap_labels)) if len(cap_labels) == 1 else None
                )

            if not cell_face_verts:
                n_skipped += 1
                continue
            new_ci = len(cell_face_lists)
            for ti in comp:
                cell_of_tet_vert[(v_in, ti)] = new_ci
            if len(components) > 1:
                n_fan_split_cells += 1
            cell_face_lists.append(cell_face_verts)
            cell_face_is_cap.append(cell_face_caps)
            cell_face_labels.append(cell_face_entity_labels)
            cell_centroid_list.append(local_cell_centroid)

    if not cell_face_lists:
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            message="dual cell 0 — 입력 mesh 가 너무 작거나 degenerate",
        )

    dual_points = np.asarray(all_points, dtype=np.float64)

    from core.utils.native_extensions import load_native_polymesh

    native_face_geometry = load_native_polymesh()
    if native_face_geometry is not None and not hasattr(native_face_geometry, "face_flip_mask"):
        native_face_geometry = None

    log.info(
        "native_poly_dual_cells",
        n_cells=len(cell_face_lists),
        n_points=dual_points.shape[0],
        skipped=n_skipped,
        nonmanifold_vertices=n_nonmanifold_vertices,
        fan_split_cells=n_fan_split_cells,
    )

    def _flip_if_inward(face: list[int], cell_centroid: np.ndarray) -> list[int]:
        """face normal 이 cell centroid 바깥 방향이면 유지, 안쪽이면 reverse."""
        pts3 = dual_points[face]
        fc = pts3.mean(axis=0)
        # 3-vertex 기반 normal
        n = np.cross(pts3[1] - pts3[0], pts3[2] - pts3[0])
        if float(np.dot(n, fc - cell_centroid)) < 0:
            return list(reversed(face))
        return face

    def _orient_faces_outward(faces: list[list[int]], owners: list[int]) -> list[list[int]]:
        if not faces:
            return []
        if native_face_geometry is None:
            return [
                _flip_if_inward(face, cell_centroid_list[owner])
                for face, owner in zip(faces, owners)
            ]
        flip_mask = np.asarray(
            native_face_geometry.face_flip_mask(
                dual_points,
                faces,
                np.asarray(owners, dtype=np.int64),
                np.asarray(cell_centroid_list, dtype=np.float64),
            ),
            dtype=bool,
        )
        return [
            list(reversed(face)) if bool(flip_mask[index]) else face
            for index, face in enumerate(faces)
        ]

    # 3a) path A (기존): ConvexHull face 정확 정점집합 dedup
    face_map: dict[tuple[int, ...], list[tuple[int, list[int]]]] = defaultdict(list)
    for ci, face_list in enumerate(cell_face_lists):
        for f in face_list:
            face_map[tuple(sorted(f))].append((ci, list(f)))

    a_i_faces: list[list[int]] = []
    a_i_own: list[int] = []
    a_i_nbr: list[int] = []
    a_b_faces: list[list[int]] = []
    a_b_own: list[int] = []
    a_b_labels: list[tuple[str, str]] = []
    for refs in face_map.values():
        if len(refs) == 2:
            (ca, fa), (cb, fb) = refs
            own, nbr = min(ca, cb), max(ca, cb)
            f_use = fa if ca == own else fb
            a_i_faces.append(f_use)
            a_i_own.append(own)
            a_i_nbr.append(nbr)
        elif len(refs) == 1:
            ci, fv = refs[0]
            a_b_faces.append(fv)
            a_b_own.append(ci)
            if classification_active:
                face_idx = cell_face_lists[ci].index(fv)
                a_b_labels.append(cell_face_labels[ci][face_idx] or ("defaultWall", "wall"))

    # 3b) path B (신규): tet edge 주위 위상적 centroid ring → internal face,
    # boundary cap 은 path A 의 hull 결과 중 surface 점을 포함한 face 만 재사용.
    b_i_faces: list[list[int]] = []
    b_i_own: list[int] = []
    b_i_nbr: list[int] = []
    for e in edge_tets:
        if e in boundary_edges_set:
            continue
        u, w = e
        ring, closed = _ordered_tet_ring(e, edge_tets, face_tets, T)
        if not closed or len(ring) < 3:
            continue
        # A closed ring is by construction one face-connected fan, so every
        # tet in it maps to the same (u, w) cell component -- resolve via
        # ring[0] rather than a stale single cell-per-vertex lookup.
        own = cell_of_tet_vert.get((u, ring[0]))
        nbr = cell_of_tet_vert.get((w, ring[0]))
        if own is None or nbr is None:
            continue
        face = [int(tet_point_id[ti]) for ti in ring]
        b_i_faces.append(face)
        b_i_own.append(own)
        b_i_nbr.append(nbr)

    # 3b') boundary-edge separating face: 인접 boundary cell 이 surface edge 를
    # 가로질러 공유해야 할 내부면 (line-511 이 skip 하던 boundary edge 를 보완).
    edge_to_btris: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for tri in boundary_faces:
        e01 = (min(tri[0], tri[1]), max(tri[0], tri[1]))
        e12 = (min(tri[1], tri[2]), max(tri[1], tri[2]))
        e20 = (min(tri[2], tri[0]), max(tri[2], tri[0]))
        for e in (e01, e12, e20):
            edge_to_btris[e].append(tri)
    for e in boundary_edges_set:
        u, w = e
        btris = edge_to_btris.get(e, [])
        if len(btris) != 2:
            # A non-manifold edge shared by >2 boundary triangles (e.g. the
            # spine of several disconnected fans meeting only along this
            # edge) has no single 2D interface to separate -- the fan split
            # above already gives each component its own closed cell, so no
            # face is needed (or well-defined) here.
            continue
        t_a, t_b = btris
        ring, _closed = _ordered_tet_ring(e, edge_tets, face_tets, T)
        if not ring:
            continue
        # Connected-component guard: the ring must actually reach both
        # boundary triangles' owning tets, i.e. t_a/t_b are face-connected
        # through this edge.  If the local tets around ``e`` are themselves
        # split into disconnected fans, the walk stops short of one end --
        # building a face from a partial ring would silently fabricate a
        # face that does not correspond to any real topological interface.
        owner_ti_a = boundary_face_tet[t_a]
        owner_ti_b = boundary_face_tet[t_b]
        if owner_ti_a not in ring or owner_ti_b not in ring:
            continue
        own = cell_of_tet_vert.get((u, ring[0]))
        nbr = cell_of_tet_vert.get((w, ring[0]))
        if own is None or nbr is None:
            continue
        raw = (
            [bface_pid[t_a]]
            + [int(tet_point_id[ti]) for ti in ring]
            + [bface_pid[t_b], bedge_pid[e]]
        )
        be_face: list[int] = []
        for pid in raw:
            if not be_face or be_face[-1] != pid:
                be_face.append(pid)
        if len(be_face) > 1 and be_face[0] == be_face[-1]:
            be_face.pop()
        if len(be_face) < 3:
            continue
        b_i_faces.append(be_face)
        b_i_own.append(own)
        b_i_nbr.append(nbr)

    # 3c) on-plane cap 필터: is_cap 은 surface 점을 하나라도 포함하면 true 이므로
    # 내부를 향한 hull face 까지 새어들어온다. 진짜 cap 은 "모든 정점이 한 입력
    # 평면 위" 인 face 뿐 — off-plane face 는 위 boundary-edge/edge-ring 이 이미
    # 내부를 닫으므로 버린다.
    surface_planes = _surface_planes(V, boundary_faces)
    surface_plane_normals = np.asarray(
        [normal for normal, _ in surface_planes],
        dtype=np.float64,
    )
    surface_plane_offsets = np.asarray(
        [offset for _, offset in surface_planes],
        dtype=np.float64,
    )

    def _is_on_plane(face: list[int], tol: float = 1e-6) -> bool:
        p = dual_points[np.asarray(face, dtype=int)]
        if not len(surface_plane_normals):
            return False
        signed_distances = p @ surface_plane_normals.T + surface_plane_offsets
        return bool(np.any(np.all(np.abs(signed_distances) < tol, axis=0)))

    b_b_faces: list[list[int]] = []
    b_b_own: list[int] = []
    b_b_labels: list[tuple[str, str]] = []
    if classification_active:
        # Garimella-style entity classification: one boundary cap per
        # classified primal boundary face and incident primal vertex.  The
        # four points are already part of the unmodified dual point set, so
        # this only refines the surface subcomplex and never moves geometry.
        #
        # Iterate boundary faces directly (rather than per-vertex) so each
        # cap resolves to the cell of the specific fan component that owns
        # the triangle's tet -- a non-manifold vertex has >1 cell and the
        # wrong choice here is exactly what corrupted the flip reference in
        # the pre-fix code (GAP: non-manifold-fan dual cell).
        for tri in boundary_faces:
            owning_tet = boundary_face_tet[tri]
            for v_in in (int(v) for v in tri):
                ci = cell_of_tet_vert.get((v_in, owning_tet))
                if ci is None:
                    continue
                others = [int(v) for v in tri if int(v) != v_in]
                if len(others) != 2:
                    continue
                edge_a = (min(v_in, others[0]), max(v_in, others[0]))
                edge_b = (min(v_in, others[1]), max(v_in, others[1]))
                raw_face = [
                    boundary_vertex_pid[v_in],
                    bedge_pid[edge_a],
                    bface_pid[tri],
                    bedge_pid[edge_b],
                ]
                face: list[int] = []
                for pid in raw_face:
                    if not face or face[-1] != pid:
                        face.append(pid)
                if len(face) >= 3:
                    b_b_faces.append(face)
                    b_b_own.append(ci)
                    b_b_labels.append(source_entity_labels[tri])
    else:
        cap_faces: list[list[int]] = []
        cap_owners: list[int] = []
        for ci in range(len(cell_face_lists)):
            for f, is_cap in zip(cell_face_lists[ci], cell_face_is_cap[ci]):
                if is_cap:
                    cap_faces.append(list(f))
                    cap_owners.append(ci)
        if (
            native_face_geometry is not None
            and hasattr(native_face_geometry, "face_plane_geometry")
            and cap_faces
        ):
            _, _, cap_on_plane = native_face_geometry.face_plane_geometry(
                dual_points,
                cap_faces,
                surface_plane_normals.reshape(-1, 3),
                surface_plane_offsets,
                1e-6,
            )
            for face, owner, is_on_plane in zip(
                cap_faces, cap_owners, np.asarray(cap_on_plane, dtype=bool)
            ):
                if bool(is_on_plane):
                    b_b_faces.append(face)
                    b_b_own.append(owner)
        else:
            for face, owner in zip(cap_faces, cap_owners):
                if _is_on_plane(face):
                    b_b_faces.append(face)
                    b_b_own.append(owner)

    a_i_faces = _orient_faces_outward(a_i_faces, a_i_own)
    a_b_faces = _orient_faces_outward(a_b_faces, a_b_own)
    b_i_faces = _orient_faces_outward(b_i_faces, b_i_own)
    b_b_faces = _orient_faces_outward(b_b_faces, b_b_own)

    # 3d) 단조 가드: on/off-plane boundary area split 으로 path 선택.
    # path B 가 void 를 늘리거나 surface coverage 를 깨면 path A 로 복귀한다.
    pre_on, pre_off = _area_split(dual_points, a_b_faces, surface_planes)
    post_on, post_off = _area_split(dual_points, b_b_faces, surface_planes)
    use_topo = (
        len(b_i_faces) > 0 and post_off <= pre_off and pre_on * 0.95 <= post_on <= pre_on * 1.05
    )
    if classification_active:
        # The classified cap subcomplex is the source-surface partition. Its
        # area is authoritative even when the legacy hull-cap area differs by
        # more than the old monotonic guard's diagnostic 5% window.
        use_topo = len(b_i_faces) > 0 and len(b_b_faces) > 0 and post_off <= pre_off + 1e-12
    log.info(
        "native_poly_dual_guard",
        pre_on=pre_on,
        pre_off=pre_off,
        post_on=post_on,
        post_off=post_off,
        classified=classification_active,
        use_topo=use_topo,
    )
    if use_topo:
        final_faces, final_owner, final_nbr, n_boundary = _order_and_concat(
            b_i_faces,
            b_i_own,
            b_i_nbr,
            b_b_faces,
            b_b_own,
        )
        final_boundary_labels = _ordered_boundary_labels(b_b_labels, b_b_own)
    else:
        final_faces, final_owner, final_nbr, n_boundary = _order_and_concat(
            a_i_faces,
            a_i_own,
            a_i_nbr,
            a_b_faces,
            a_b_own,
        )
        final_boundary_labels = _ordered_boundary_labels(a_b_labels, a_b_own)
    n_internal = len(final_faces) - n_boundary

    boundary_entries: list[dict[str, Any]] | None = None
    if classification_active:
        if len(final_boundary_labels) != n_boundary:
            return PolyDualResult(
                False,
                time.perf_counter() - t0,
                message=(
                    "classified dual boundary label count mismatch: "
                    f"{len(final_boundary_labels)} != {n_boundary}"
                ),
            )
        grouped_b_faces, grouped_b_owner, boundary_entries = _group_classified_boundary_faces(
            final_faces[n_internal:],
            final_owner[n_internal:],
            final_boundary_labels,
            n_internal,
        )
        final_faces = final_faces[:n_internal] + grouped_b_faces
        final_owner = final_owner[:n_internal] + grouped_b_owner

    invalid_star_cells, invalid_star_subtets, star_examples = _star_validity(
        dual_points,
        final_faces,
        final_owner,
        final_nbr,
        len(cell_face_lists),
    )
    if invalid_star_cells:
        log.warning(
            "native_poly_dual_star_invalid",
            invalid_cells=invalid_star_cells,
            invalid_subtets=invalid_star_subtets,
            examples=star_examples,
        )
        if _dual_point_mode == "garimella":
            fallback = tet_to_poly_dual(
                original_V,
                T,
                case_dir,
                min_cell_verts=min_cell_verts,
                boundary_face_labels=boundary_face_labels,
                boundary_face_entities=boundary_face_entities,
                boundary_face_classifier=boundary_face_classifier,
                _dual_point_mode="centroid",
            )
            if fallback.success:
                fallback.message = (
                    f"{fallback.message}; garimella point candidate rejected: "
                    f"star_invalid_cells={invalid_star_cells}, "
                    f"star_invalid_subtets={invalid_star_subtets}"
                )
                return fallback
            fallback.message = (
                f"{fallback.message}; garimella point candidate rejected: "
                f"star_invalid_cells={invalid_star_cells}, "
                f"star_invalid_subtets={invalid_star_subtets}"
            )
            return fallback
        return PolyDualResult(
            False,
            time.perf_counter() - t0,
            n_cells=len(cell_face_lists),
            n_points=int(dual_points.shape[0]),
            n_faces=len(final_faces),
            message=(
                "star_validity_refused: mode=centroid, "
                f"invalid_cells={invalid_star_cells}, "
                f"invalid_subtets={invalid_star_subtets}"
            ),
            invalid_star_cells=invalid_star_cells,
            invalid_star_subtets=invalid_star_subtets,
            star_examples=star_examples,
        )

    # 5) polyMesh 쓰기
    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)
    from core.generator.tier_layers_post import (  # noqa: PLC0415
        _ensure_minimal_controldict,
        _write_minimal_fv_dicts,
    )

    _ensure_minimal_controldict(case_dir)
    _write_minimal_fv_dicts(case_dir)
    from core.layers.native_bl import (  # noqa: PLC0415
        _write_boundary,
        _write_faces,
        _write_labels,
        _write_points,
    )

    _write_points(poly_dir / "points", dual_points)
    _write_faces(poly_dir / "faces", final_faces)
    _write_labels(
        poly_dir / "owner",
        np.array(final_owner, dtype=np.int64),
        "owner",
    )
    _write_labels(
        poly_dir / "neighbour",
        np.array(final_nbr, dtype=np.int64),
        "neighbour",
    )
    _write_boundary(
        poly_dir / "boundary",
        boundary_entries
        or [
            {
                "name": "defaultWall",
                "type": "wall",
                "nFaces": n_boundary,
                "startFace": n_internal,
            }
        ],
    )

    elapsed = time.perf_counter() - t0
    return PolyDualResult(
        success=True,
        elapsed=elapsed,
        n_cells=len(cell_face_lists),
        n_points=int(dual_points.shape[0]),
        n_faces=len(final_faces),
        message=(
            f"tet→poly dual OK — cells={len(cell_face_lists)}, "
            f"points={dual_points.shape[0]}, faces={len(final_faces)}, "
            f"skipped_cells={n_skipped}, "
            f"star_invalid_cells={invalid_star_cells}, "
            f"star_invalid_subtets={invalid_star_subtets}"
        ),
        invalid_star_cells=invalid_star_cells,
        invalid_star_subtets=invalid_star_subtets,
        star_examples=star_examples,
    )
