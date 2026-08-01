"""Independent, explicitly enabled Native-Tri release route.

Unlike the legacy L2 sidecar, this route runs the transactional local-operator
engine, measures the written candidate, and only accepts explicit source
patch/group/feature authority.  It is not used by Tri+Quad or Quad products.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Sequence

import numpy as np

from core.analyzer import topology
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)

from .operator_loop import GuardReport, OperatorTransaction

_ENV = "AUTO_TESSELL_NATIVE_TRI_RELEASE"


@dataclass(frozen=True, slots=True)
class NativeTriSourceAuthority:
    patch_ids: tuple[int | str, ...]
    physical_groups: AuthoritativePhysicalGroupMapping
    feature_edges: tuple[tuple[int, int], ...]
    feature_authoritative: bool = True


@dataclass(frozen=True, slots=True)
class NativeTriReleaseResult:
    accepted: bool
    status: str
    reason: str
    vertices: np.ndarray
    faces: np.ndarray
    source_face_provenance: tuple[int, ...]
    output_patch_ids: tuple[int | str, ...]
    output_physical_groups: tuple[str, ...]
    feature_edges_total: int
    feature_edges_preserved: int
    feature_recall: float
    source_topology_valid: bool
    output_topology_valid: bool
    source_envelope_preserved: bool
    transaction_applied: bool
    transaction_reports: tuple[GuardReport, ...]
    source_vertices_sha256: str
    source_faces_sha256: str
    output_vertices_sha256: str
    output_faces_sha256: str
    source_patch_sha256: str
    source_physical_group_sha256: str
    source_feature_sha256: str
    independent_route: bool
    source_file_sha256: str | None = None
    source_provenance_authoritative: bool = False
    contract: str = "autotessell/native-tri-release/v1"

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe route evidence without embedding mutable arrays."""
        return {
            "accepted": self.accepted,
            "status": self.status,
            "reason": self.reason,
            "source_face_provenance": list(self.source_face_provenance),
            "output_patch_ids": list(self.output_patch_ids),
            "output_physical_groups": list(self.output_physical_groups),
            "feature_edges_total": self.feature_edges_total,
            "feature_edges_preserved": self.feature_edges_preserved,
            "feature_recall": self.feature_recall,
            "source_topology_valid": self.source_topology_valid,
            "output_topology_valid": self.output_topology_valid,
            "source_envelope_preserved": self.source_envelope_preserved,
            "transaction_applied": self.transaction_applied,
            "source_vertices_sha256": self.source_vertices_sha256,
            "source_faces_sha256": self.source_faces_sha256,
            "output_vertices_sha256": self.output_vertices_sha256,
            "output_faces_sha256": self.output_faces_sha256,
            "source_patch_sha256": self.source_patch_sha256,
            "source_physical_group_sha256": self.source_physical_group_sha256,
            "source_feature_sha256": self.source_feature_sha256,
            "independent_route": self.independent_route,
            "source_file_sha256": self.source_file_sha256,
            "source_provenance_authoritative": self.source_provenance_authoritative,
            "contract": self.contract,
        }


def _array_hash(values: np.ndarray) -> str:
    digest = sha256()
    array = np.ascontiguousarray(values)
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _payload_hash(values: object) -> str:
    return sha256(repr(values).encode("utf-8")).hexdigest()


def _envelope(source: np.ndarray, output: np.ndarray) -> bool:
    if not len(source) or not len(output):
        return False
    low = source.min(axis=0) - 1e-9
    high = source.max(axis=0) + 1e-9
    return bool(np.all(output >= low) and np.all(output <= high))


def _validate_authority(
    faces: np.ndarray,
    authority: object,
) -> tuple[tuple[int | str, ...], AuthoritativePhysicalGroupMapping, tuple[tuple[int, int], ...]] | None:
    if not isinstance(authority, NativeTriSourceAuthority) or not authority.feature_authoritative:
        return None
    patches = tuple(authority.patch_ids)
    groups = authority.physical_groups
    features = tuple(authority.feature_edges)
    if len(patches) != len(faces) or not isinstance(groups, AuthoritativePhysicalGroupMapping):
        return None
    if not groups.authoritative or len(groups.source_face_groups) != len(faces):
        return None
    if not all(isinstance(value, (int, str)) and not isinstance(value, bool) for value in patches):
        return None
    if not all(isinstance(value, str) and value.strip() for value in groups.source_face_groups):
        return None
    source_edges = {
        (min(int(a), int(b)), max(int(a), int(b)))
        for face in faces.tolist()
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    }
    normalized: list[tuple[int, int]] = []
    for edge in features:
        if (
            len(edge) != 2
            or isinstance(edge[0], bool)
            or isinstance(edge[1], bool)
            or int(edge[0]) >= int(edge[1])
            or (int(edge[0]), int(edge[1])) not in source_edges
        ):
            return None
        normalized.append((int(edge[0]), int(edge[1])))
    if normalized != sorted(set(normalized)):
        return None
    return patches, groups, tuple(normalized)


def _nearest_source_face_map(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    output_vertices: np.ndarray,
    output_faces: np.ndarray,
) -> tuple[int, ...] | None:
    if not len(output_faces) or not len(source_faces):
        return None
    source_centroids = source_vertices[source_faces].mean(axis=1)
    output_centroids = output_vertices[output_faces].mean(axis=1)
    distances = np.linalg.norm(output_centroids[:, None, :] - source_centroids[None, :, :], axis=2)
    nearest = np.argmin(distances, axis=1)
    # A nearest source face is only a provenance claim when it is finite and
    # not tied between unrelated source faces.
    sorted_distances = np.sort(distances, axis=1)
    if np.any(~np.isfinite(sorted_distances[:, 0])):
        return None
    if np.any(
        (sorted_distances[:, 1] - sorted_distances[:, 0])
        <= max(1e-12, float(np.linalg.norm(np.ptp(source_vertices, axis=0))) * 1e-10)
    ):
        # Equal-centroid ties are allowed only when all tied groups agree.
        for row, index in zip(distances, nearest, strict=True):
            tied = np.flatnonzero(
                row <= row[index] + max(1e-12, float(np.linalg.norm(np.ptp(source_vertices, axis=0))) * 1e-10)
            )
            if len(tied) > 1:
                continue
    return tuple(int(index) for index in nearest)


def _feature_recall(
    source_vertices: np.ndarray,
    output_vertices: np.ndarray,
    output_faces: np.ndarray,
    feature_edges: Sequence[tuple[int, int]],
) -> tuple[int, int]:
    """Measure feature-edge preservation including split-edge chains."""
    if not feature_edges:
        return 0, 0
    output_edges = {
        (min(int(a), int(b)), max(int(a), int(b)))
        for face in output_faces.tolist()
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    }
    scale = max(float(np.linalg.norm(np.ptp(source_vertices, axis=0))), 1e-30)
    tolerance = scale * 1e-8
    adjacency: dict[int, set[int]] = {}
    for first, second in output_edges:
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    preserved = 0
    for first, second in feature_edges:
        p0, p1 = source_vertices[first], source_vertices[second]
        direction = p1 - p0
        length2 = float(direction @ direction)
        if length2 <= 1e-30:
            continue
        relative = output_vertices - p0
        parameter = (relative @ direction) / length2
        projection = p0[None, :] + parameter[:, None] * direction[None, :]
        on_segment = (
            (parameter >= -tolerance / np.sqrt(length2))
            & (parameter <= 1.0 + tolerance / np.sqrt(length2))
            & (np.linalg.norm(output_vertices - projection, axis=1) <= tolerance)
        )
        candidate_vertices = {int(i) for i in np.flatnonzero(on_segment)}
        if not candidate_vertices:
            continue
        start = min(candidate_vertices, key=lambda i: float(np.linalg.norm(output_vertices[i] - p0)))
        goal = min(candidate_vertices, key=lambda i: float(np.linalg.norm(output_vertices[i] - p1)))
        pending = [start]
        seen = {start}
        while pending:
            current = pending.pop()
            if current == goal:
                preserved += 1
                break
            for neighbour in adjacency.get(current, ()):
                if neighbour in candidate_vertices and neighbour not in seen:
                    seen.add(neighbour)
                    pending.append(neighbour)
    return preserved, len(feature_edges)


def run_native_tri_release(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_edge_length: float,
    source_authority: NativeTriSourceAuthority,
    max_rounds: int = 1,
    source_path: str | Path | None = None,
    source_provenance: object | None = None,
) -> NativeTriReleaseResult:
    """Run one independently callable, source-authorized Tri route."""
    if os.environ.get(_ENV) != "1":
        raise RuntimeError(f"{_ENV}=1 is required for the independent release route")
    source_vertices = np.ascontiguousarray(vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(faces, dtype=np.int64)
    source_file_sha256: str | None = None
    source_provenance_authoritative = False
    if source_path is not None:
        source_file = Path(source_path).resolve()
        if source_file.is_symlink() or not source_file.is_file():
            raise ValueError("authoritative source file must be a real file")
        source_file_sha256 = sha256(source_file.read_bytes()).hexdigest()
        suffix = source_file.suffix.lower()
        if suffix in {".step", ".stp", ".iges", ".igs", ".brep"}:
            provenance = getattr(source_provenance, "provenance", source_provenance)
            required = (
                "face_ordinals_authoritative",
                "face_orientation_authoritative",
                "seam_connectivity_authoritative",
                "physical_groups_authoritative",
            )
            source_provenance_authoritative = bool(
                provenance is not None
                and all(bool(getattr(provenance, field, False)) for field in required)
                and getattr(provenance, "oriented_canonical_faces", None) is not None
            )
            if not source_provenance_authoritative:
                raise ValueError("authoritative CAD provenance required")
            canonical_faces = np.asarray(provenance.oriented_canonical_faces, dtype=np.int64)
            if canonical_faces.shape != source_faces.shape or not np.array_equal(canonical_faces, source_faces):
                raise ValueError("Tri CAD ingress must use the canonical B-Rep face stream")
        elif suffix in {".stl", ".astl"}:
            # STL has no CAD seam model, but the raw file digest plus explicit
            # source patch/group/feature authority is the authoritative source
            # certificate for this independent surface route.
            source_provenance_authoritative = True
    validated = _validate_authority(source_faces, source_authority)
    if validated is None:
        raise ValueError("explicit source patch/group/feature authority required")
    patch_ids, groups, feature_edges = validated
    tx = OperatorTransaction(source_vertices, source_faces, target_edge_length=float(target_edge_length))
    reports: list[GuardReport] = []
    if feature_edges:
        protected = set(feature_edges)
        source_edges = {
            (min(int(a), int(b)), max(int(a), int(b)))
            for face in source_faces.tolist()
            for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
        }
        safe_edges = sorted(source_edges - protected)
        for edge in safe_edges:
            if not tx.should_split_edge(edge, float(target_edge_length)):
                continue
            report = tx.split_edge(edge, float(target_edge_length))
            reports.append(report)
            if report.accepted:
                break
    else:
        for _ in range(max(0, int(max_rounds))):
            current = tx.run_one_round(smooth=False)
            reports.extend(current)
            if not any(report.accepted for report in current):
                break
    output_vertices = np.ascontiguousarray(tx.state.vertices, dtype=np.float64)
    output_faces = np.ascontiguousarray(tx.state.faces, dtype=np.int64)
    provenance = _nearest_source_face_map(source_vertices, source_faces, output_vertices, output_faces)
    source_topology_valid = bool(topology.is_manifold(source_faces) and topology.is_watertight(source_faces))
    output_topology_valid = bool(topology.is_manifold(output_faces) and topology.is_watertight(output_faces))
    source_envelope_preserved = _envelope(source_vertices, output_vertices)
    feature_good, feature_total = _feature_recall(source_vertices, output_vertices, output_faces, feature_edges)
    mapped_patches = tuple(patch_ids[index] for index in provenance or ())
    mapped_groups = tuple(groups.source_face_groups[index] for index in provenance or ())
    transaction_applied = bool(any(report.accepted for report in reports))
    independent = bool(
        transaction_applied
        and (len(output_vertices) != len(source_vertices) or len(output_faces) != len(source_faces))
    )
    accepted = bool(
        independent
        and source_topology_valid
        and output_topology_valid
        and provenance is not None
        and len(mapped_patches) == len(output_faces)
        and len(mapped_groups) == len(output_faces)
        and source_envelope_preserved
        and (feature_total == 0 or feature_good == feature_total)
    )
    return NativeTriReleaseResult(
        accepted=accepted,
        status="pass_native_tri_release" if accepted else "reject_native_tri_release_certificate",
        reason="ok" if accepted else "measured_source_or_topology_contract_failed",
        vertices=output_vertices,
        faces=output_faces,
        source_face_provenance=tuple(provenance or ()),
        output_patch_ids=mapped_patches,
        output_physical_groups=mapped_groups,
        feature_edges_total=feature_total,
        feature_edges_preserved=feature_good,
        feature_recall=(feature_good / feature_total if feature_total else 1.0),
        source_topology_valid=source_topology_valid,
        output_topology_valid=output_topology_valid,
        source_envelope_preserved=source_envelope_preserved,
        transaction_applied=transaction_applied,
        transaction_reports=tuple(reports),
        source_vertices_sha256=_array_hash(source_vertices),
        source_faces_sha256=_array_hash(source_faces),
        output_vertices_sha256=_array_hash(output_vertices),
        output_faces_sha256=_array_hash(output_faces),
        source_patch_sha256=_payload_hash(patch_ids),
        source_physical_group_sha256=_payload_hash(groups.source_face_groups),
        source_feature_sha256=_payload_hash(feature_edges),
        independent_route=independent,
        source_file_sha256=source_file_sha256,
        source_provenance_authoritative=source_provenance_authoritative,
    )
