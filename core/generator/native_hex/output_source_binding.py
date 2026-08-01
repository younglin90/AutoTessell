"""Measured Hex output-boundary to authoritative source-BRep binding.

The native Hex grid may only claim CAD boundary authority when the caller
supplies canonical source triangles, B-Rep face ordinals, and authoritative
physical-group names.  Geometry-only inputs remain explicitly unverified.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Sequence

import numpy as np


_HEX_FACES: tuple[tuple[int, int, int, int], ...] = (
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (3, 7, 6, 2),
    (0, 4, 7, 3),
    (1, 2, 6, 5),
)


@dataclass(frozen=True, slots=True)
class HexMeasuredSourceBinding:
    """Measured, serializable evidence for one written Hex boundary."""

    status: str
    source_brep_authoritative: bool
    physical_groups_authoritative: bool
    output_boundary_face_count: int
    mapping_complete: bool
    physical_group_mapping_complete: bool
    strict_binding_complete: bool
    output_boundary_face_ids_sha256: str | None
    output_to_source_face_sha256: str | None
    output_physical_group_sha256: str | None
    source_file_sha256: str | None
    max_source_plane_distance: float | None
    tolerance: float | None
    output_face_to_source_face: tuple[int, ...]
    output_physical_groups: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    contract: str = "autotessell/native-hex-source-binding/v1"

    @property
    def accepted(self) -> bool:
        return self.strict_binding_complete

    def as_dict(self) -> dict[str, object]:
        # Return JSON-safe measured binding evidence.
        value = asdict(self)
        value["accepted"] = self.accepted
        return value


def _array_hash(value: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(value.dtype).encode("ascii"))
    digest.update(np.asarray(value.shape, dtype="<i8").tobytes())
    digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()


def _group_hash(value: Sequence[str]) -> str:
    return sha256(
        json.dumps(tuple(value), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _point_triangle_distances(point: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Return true Euclidean distances from one point to source triangles."""
    p = np.asarray(point, dtype=np.float64)
    tri = np.asarray(triangles, dtype=np.float64)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab = b - a
    ac = c - a
    normal = np.cross(ab, ac)
    normal_sq = np.einsum("ij,ij->i", normal, normal)
    signed = np.einsum("ij,ij->i", normal, p[None, :] - a)
    projection = p[None, :] - normal * (signed / np.maximum(normal_sq, 1e-30))[:, None]
    v0 = ab
    v1 = ac
    v2 = projection - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)
    denominator = np.maximum(d00 * d11 - d01 * d01, 1e-30)
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    inside = (v >= 0.0) & (w >= 0.0) & (v + w <= 1.0)

    def segment_distance(end: np.ndarray) -> np.ndarray:
        direction = end - a
        length_sq = np.einsum("ij,ij->i", direction, direction)
        parameter = np.einsum("ij,ij->i", p[None, :] - a, direction) / np.maximum(length_sq, 1e-30)
        parameter = np.clip(parameter, 0.0, 1.0)
        closest = a + parameter[:, None] * direction
        return np.linalg.norm(p[None, :] - closest, axis=1)

    plane_distance = np.abs(signed) / np.sqrt(np.maximum(normal_sq, 1e-30))
    edge_distance = np.minimum(segment_distance(b), np.minimum(segment_distance(c), segment_distance(a)))
    return np.where(inside, plane_distance, edge_distance)


def _source_file_hash(source_path: str | Path | None) -> str | None:
    if source_path is None:
        return None
    path = Path(source_path)
    if not path.is_file() or path.is_symlink():
        return None
    return sha256(path.read_bytes()).hexdigest()


def extract_hex_boundary_faces(hexes: np.ndarray) -> tuple[tuple[int, ...], ...]:
    """Return unique boundary quads in deterministic sorted-key order."""
    cells = np.asarray(hexes, dtype=np.int64)
    owners: dict[tuple[int, ...], list[int]] = {}
    oriented: dict[tuple[int, ...], tuple[int, ...]] = {}
    for cell in cells:
        for local in _HEX_FACES:
            face = tuple(int(cell[index]) for index in local)
            key = tuple(sorted(face))
            owners.setdefault(key, []).append(1)
            oriented.setdefault(key, face)
    boundary = [key for key, owners_for_face in owners.items() if len(owners_for_face) == 1]
    return tuple(oriented[key] for key in sorted(boundary))


def _invalid(
    *,
    status: str,
    count: int,
    source_file_sha256: str | None,
    missing: tuple[str, ...],
) -> HexMeasuredSourceBinding:
    return HexMeasuredSourceBinding(
        status=status,
        source_brep_authoritative=False,
        physical_groups_authoritative=False,
        output_boundary_face_count=count,
        mapping_complete=False,
        physical_group_mapping_complete=False,
        strict_binding_complete=False,
        output_boundary_face_ids_sha256=None,
        output_to_source_face_sha256=None,
        output_physical_group_sha256=None,
        source_file_sha256=source_file_sha256,
        max_source_plane_distance=None,
        tolerance=None,
        output_face_to_source_face=(),
        output_physical_groups=(),
        missing_evidence=missing,
    )


def measure_hex_source_binding(
    output_vertices: np.ndarray,
    hexes: np.ndarray,
    *,
    source_vertices: np.ndarray | None,
    source_faces: np.ndarray | None,
    source_face_ordinals: np.ndarray | None,
    physical_group_names: Sequence[str] | None,
    source_brep_authoritative: bool,
    physical_groups_authoritative: bool,
    source_path: str | Path | None = None,
    plane_tolerance: float | None = None,
) -> HexMeasuredSourceBinding:
    """Map every output boundary quad to one authoritative source face.

    The release binding is deliberately limited to planar source support:
    each output boundary centroid must lie on the selected source triangle's
    plane and have a compatible normal.  Curved/stair-step geometry remains
    unverified instead of being relabeled by nearest-neighbour inference.
    """
    boundary = extract_hex_boundary_faces(np.asarray(hexes, dtype=np.int64))
    source_hash = _source_file_hash(source_path)
    if not source_brep_authoritative:
        return _invalid(
            status="reject_source_brep_authority_unavailable",
            count=len(boundary),
            source_file_sha256=source_hash,
            missing=("source_brep", "output_boundary_face_to_source_brep"),
        )
    if not physical_groups_authoritative:
        return _invalid(
            status="reject_source_physical_groups_unavailable",
            count=len(boundary),
            source_file_sha256=source_hash,
            missing=("physical_group",),
        )
    if (
        source_vertices is None
        or source_faces is None
        or source_face_ordinals is None
        or physical_group_names is None
    ):
        return _invalid(
            status="reject_source_binding_payload_missing",
            count=len(boundary),
            source_file_sha256=source_hash,
            missing=("source_triangles", "source_face_ordinals", "physical_group"),
        )

    points = np.asarray(output_vertices, dtype=np.float64)
    sv = np.asarray(source_vertices, dtype=np.float64)
    sf = np.asarray(source_faces, dtype=np.int64)
    ordinals = np.asarray(source_face_ordinals, dtype=np.int64)
    groups = tuple(physical_group_names)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or sv.ndim != 2
        or sv.shape[1] != 3
        or sf.ndim != 2
        or sf.shape[1] != 3
        or len(ordinals) != len(sf)
        or np.any(sf < 0)
        or np.any(sf >= len(sv))
        or len(groups) == 0
        or any(not isinstance(name, str) or not name.strip() for name in groups)
        or np.any(ordinals < 0)
        or np.any(ordinals >= len(groups))
    ):
        return _invalid(
            status="reject_source_binding_payload_invalid",
            count=len(boundary),
            source_file_sha256=source_hash,
            missing=("source_triangles", "source_face_ordinals", "physical_group"),
        )

    source_triangles = sv[sf]
    source_normals = np.cross(
        source_triangles[:, 1] - source_triangles[:, 0],
        source_triangles[:, 2] - source_triangles[:, 0],
    )
    source_norm = np.linalg.norm(source_normals, axis=1)
    valid_source = source_norm > 1e-15
    if not np.any(valid_source):
        return _invalid(
            status="reject_degenerate_source_triangles",
            count=len(boundary),
            source_file_sha256=source_hash,
            missing=("source_triangles",),
        )
    source_unit = np.zeros_like(source_normals)
    source_unit[valid_source] = source_normals[valid_source] / source_norm[valid_source, None]
    source_centroids = source_triangles.mean(axis=1)
    diag = float(np.linalg.norm(sv.max(axis=0) - sv.min(axis=0))) if len(sv) else 0.0
    tolerance = float(plane_tolerance or max(1e-9, diag * 1e-8))
    output_ids = np.arange(len(boundary), dtype=np.int64)
    mappings: list[int] = []
    output_groups: list[str] = []
    distances: list[float] = []
    complete = True
    output_points = np.asarray(points)
    for face in boundary:
        face_points = output_points[np.asarray(face, dtype=np.int64)]
        centroid = face_points.mean(axis=0)
        normal = np.cross(face_points[1] - face_points[0], face_points[2] - face_points[0])
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-15:
            complete = False
            continue
        unit = normal / norm
        distances_all = _point_triangle_distances(centroid, source_triangles)
        orientation_penalty = 1.0 - np.abs(source_unit @ unit)
        score = distances_all / max(tolerance, 1e-30) + orientation_penalty * 10.0
        score[~valid_source] = np.inf
        source_index = int(np.argmin(score))
        distance = float(distances_all[source_index])
        compatible = bool(
            np.isfinite(score[source_index])
            and distance <= tolerance
            and abs(float(source_unit[source_index] @ unit)) >= 0.75
        )
        if not compatible:
            complete = False
        mappings.append(int(ordinals[source_index]))
        output_groups.append(groups[int(ordinals[source_index])])
        distances.append(distance)

    mapping_complete = complete and len(mappings) == len(boundary)
    groups_complete = mapping_complete and len(output_groups) == len(boundary)
    return HexMeasuredSourceBinding(
        status=(
            "pass_measured_native_hex_source_binding"
            if mapping_complete and groups_complete
            else "reject_native_hex_source_binding_geometry"
        ),
        source_brep_authoritative=True,
        physical_groups_authoritative=True,
        output_boundary_face_count=len(boundary),
        mapping_complete=mapping_complete,
        physical_group_mapping_complete=groups_complete,
        strict_binding_complete=mapping_complete and groups_complete,
        output_boundary_face_ids_sha256=_array_hash(output_ids),
        output_to_source_face_sha256=_array_hash(np.asarray(mappings, dtype=np.int64)),
        output_physical_group_sha256=_group_hash(output_groups),
        source_file_sha256=source_hash,
        max_source_plane_distance=max(distances) if distances else None,
        tolerance=tolerance,
        output_face_to_source_face=tuple(mappings),
        output_physical_groups=tuple(output_groups),
        missing_evidence=() if mapping_complete and groups_complete else ("output_boundary_face_to_source_brep",),
    )


def make_boundary_patch_classifier(
    evidence: HexMeasuredSourceBinding,
    hexes: np.ndarray,
) -> Callable[[list[int], np.ndarray], str | None]:
    """Return a deterministic generic-writer patch classifier for measured evidence."""
    boundary = extract_hex_boundary_faces(np.asarray(hexes, dtype=np.int64))
    lookup = {
        tuple(sorted(face)): evidence.output_physical_groups[index]
        for index, face in enumerate(boundary)
        if index < len(evidence.output_physical_groups)
    }

    def classify(face: list[int], _vertices: np.ndarray) -> str | None:
        return lookup.get(tuple(sorted(int(value) for value in face)))

    return classify
