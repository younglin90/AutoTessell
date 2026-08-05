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
from collections.abc import Mapping
from typing import Sequence

import numpy as np

from core.analyzer import topology
from core.evaluator.surface_physical_group_provenance import (
    AuthoritativePhysicalGroupMapping,
)
from core.utils.native_extensions import load_native_tri_quality_repair

from .operator_loop import GuardReport, OperatorKind, OperatorTransaction

_ENV = "AUTO_TESSELL_NATIVE_TRI_RELEASE"
_NACA_QUALITY_REPAIR_ENV = "AUTO_TESSELL_NATIVE_TRI_NACA_QUALITY_REPAIR"
_NACA_FAN_PATCH_ENV = "AUTO_TESSELL_NATIVE_TRI_NACA_FAN_PATCH"
_QUALITY_ADMISSION_ENV = "AUTO_TESSELL_NATIVE_TRI_QUALITY_ADMISSION"


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
    source_certificate_sha256: str | None = None
    source_semantic_ledger_sha256: str | None = None
    contract: str = "autotessell/native-tri-release/v1"
    quality_repair: dict[str, object] | None = None
    quality_admission: dict[str, object] | None = None
    fan_patch: dict[str, object] | None = None

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
            "source_certificate_sha256": self.source_certificate_sha256,
            "source_semantic_ledger_sha256": self.source_semantic_ledger_sha256,
            "contract": self.contract,
            "quality_repair": self.quality_repair,
            "quality_admission": self.quality_admission,
            "fan_patch": self.fan_patch,
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



def _json_safe_quality_value(value: object) -> object:
    """Convert a pybind quality receipt to deterministic JSON-safe values."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe_quality_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_quality_value(item) for item in value]
    return value


def _make_naca_quality_admission(
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    receipts: list[dict[str, object]],
):
    """Build the explicit C++23 quality-admission callback for NACA only."""
    module = load_native_tri_quality_repair()
    if module is None or not hasattr(module, "admit_surface_edit"):
        raise RuntimeError("native_tri_quality_admission_unavailable")
    source_points = np.ascontiguousarray(source_vertices, dtype=np.float64)
    support_faces = np.ascontiguousarray(source_faces, dtype=np.int64)

    def admit(before, after, operator, _face_correspondence):
        raw = module.admit_surface_edit(
            np.ascontiguousarray(before.vertices, dtype=np.float64),
            np.ascontiguousarray(before.faces, dtype=np.int64),
            np.ascontiguousarray(after.vertices, dtype=np.float64),
            np.ascontiguousarray(after.faces, dtype=np.int64),
            source_points,
            support_faces,
        )
        row = _json_safe_quality_value(dict(raw))
        if not isinstance(row, dict):
            return False, "quality_admission_malformed_receipt"
        row["operator"] = str(getattr(operator, "value", operator))
        receipts.append(row)
        accepted = row.get("accepted")
        if isinstance(accepted, (bool, np.bool_)) and accepted:
            return True, str(row.get("reason", "strict_quality_improvement"))
        return False, str(row.get("reason", "quality_admission_refused"))

    return admit


def _run_naca_fan_patch(
    tx: OperatorTransaction,
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    source_path: str | Path | None,
    reports: list[GuardReport],
    quality_enabled: bool,
) -> dict[str, object] | None:
    """Submit one deterministic C++ worst-fan retriangulation transaction.

    The experimental lane is deliberately NACA-only and requires the explicit
    C++ quality-admission callback.  The proposal reuses all committed
    vertices, replaces only closed degree-two fan neighborhoods, and is still
    accepted only through the normal transaction guards.
    """
    if os.environ.get(_NACA_FAN_PATCH_ENV) != "1":
        return None
    if source_path is None or Path(source_path).stem.lower() != "naca0012":
        return None
    if not quality_enabled:
        return {
            "schema": "autotessell/native-tri-worst-fan-patch/v1",
            "accepted": False,
            "status": "fan_patch_refused",
            "reason": "quality_admission_required",
        }
    module = load_native_tri_quality_repair()
    if module is None or not hasattr(module, "propose_worst_fan_patch"):
        raise RuntimeError("native_tri_worst_fan_patch_unavailable")
    before_vertices = np.ascontiguousarray(tx.state.vertices, dtype=np.float64)
    before_faces = np.ascontiguousarray(tx.state.faces, dtype=np.int64)
    raw = module.propose_worst_fan_patch(
        before_vertices,
        before_faces,
        2,
        16,
    )
    payload = _json_safe_quality_value(dict(raw))
    if not isinstance(payload, dict):
        raise RuntimeError("native_tri_worst_fan_patch_malformed_receipt")
    if not bool(payload.get("accepted", False)):
        return payload
    candidate_vertices = np.ascontiguousarray(
        np.asarray(payload.get("candidate_vertices"), dtype=np.float64),
    )
    candidate_faces = np.ascontiguousarray(
        np.asarray(payload.get("candidate_faces"), dtype=np.int64),
    )
    if (
        candidate_vertices.shape != before_vertices.shape
        or not np.isfinite(candidate_vertices).all()
        or not np.array_equal(candidate_vertices, before_vertices)
    ):
        raise RuntimeError("native_tri_worst_fan_patch_vertex_identity_failed")
    if (
        candidate_faces.ndim != 2
        or candidate_faces.shape[1] != 3
        or not len(candidate_faces)
        or candidate_faces.min() < 0
        or candidate_faces.max() >= len(candidate_vertices)
    ):
        raise RuntimeError("native_tri_worst_fan_patch_candidate_faces_invalid")
    correspondence_values = payload.get("face_correspondence")
    if not isinstance(correspondence_values, list) or not correspondence_values:
        raise RuntimeError("native_tri_worst_fan_patch_correspondence_missing")
    correspondence = tuple(
        (int(row[0]), int(row[1]))
        for row in correspondence_values
        if isinstance(row, list) and len(row) == 2
    )
    if (
        len(correspondence) != len(correspondence_values)
        or len({new_index for _, new_index in correspondence}) != len(correspondence)
        or any(
            old_index < 0
            or old_index >= len(before_faces)
            or new_index < 0
            or new_index >= len(candidate_faces)
            for old_index, new_index in correspondence
        )
    ):
        raise RuntimeError("native_tri_worst_fan_patch_correspondence_invalid")
    guard = tx.attempt(
        OperatorKind.COLLAPSE,
        (candidate_vertices, candidate_faces),
        face_correspondence=correspondence,
    )
    reports.append(guard)
    payload["transaction_guard"] = {
        "accepted": bool(guard.accepted),
        "operator": str(guard.operator),
        "reason": guard.reason,
    }
    payload["transaction_applied"] = bool(guard.accepted)
    payload["candidate_face_count"] = int(len(candidate_faces))
    payload["candidate_vertex_count"] = int(len(candidate_vertices))
    return payload


def _run_naca_quality_repair(
    tx: OperatorTransaction,
    source_vertices: np.ndarray,
    source_faces: np.ndarray,
    source_path: str | Path | None,
    reports: list[GuardReport],
) -> dict[str, object] | None:
    """Run the opt-in C++ repair only for the measured NACA release case.

    The native kernel never owns publication: its candidate is submitted back
    through the same transaction guard that protects the original route.
    """
    if os.environ.get(_NACA_QUALITY_REPAIR_ENV) != "1":
        return None
    if source_path is None or Path(source_path).stem.lower() != "naca0012":
        return None
    repair_module = load_native_tri_quality_repair()
    if repair_module is None:
        raise RuntimeError("native_tri_naca_quality_repair_unavailable")
    points = np.ascontiguousarray(tx.state.vertices, dtype=np.float64)
    faces = np.ascontiguousarray(tx.state.faces, dtype=np.int64)
    source_points = np.ascontiguousarray(source_vertices, dtype=np.float64)
    support_faces = np.ascontiguousarray(source_faces, dtype=np.int64)
    locked_vertices = np.zeros(len(points), dtype=np.uint8)
    raw = repair_module.repair_surface_quality(
        points,
        faces,
        source_points,
        support_faces,
        locked_vertices,
        max_iterations=96,
        minimum_angle=10.0,
        maximum_angle=150.0,
        minimum_mean_ratio=0.05,
    )
    raw_dict = dict(raw)
    candidate_payload = raw_dict.pop("candidate_vertices", None)
    snapshot_payload = raw_dict.pop("accepted_snapshots", None)
    report = _json_safe_quality_value(raw_dict)
    if not isinstance(report, dict):
        raise RuntimeError("native_tri_naca_quality_repair_malformed_receipt")
    if not bool(report.get("accepted", False)):
        raise RuntimeError(
            "native_tri_naca_quality_repair_refused:"
            f"{report.get('reason', 'unknown')}"
        )
    candidate = np.ascontiguousarray(np.asarray(candidate_payload, dtype=np.float64))
    if candidate.shape != points.shape or not np.isfinite(candidate).all():
        raise RuntimeError("native_tri_naca_quality_repair_candidate_shape_or_finite_failed")
    if not bool(report.get("faces_unchanged", False)):
        raise RuntimeError("native_tri_naca_quality_repair_faces_changed")
    if snapshot_payload is None:
        snapshot_payload = [candidate_payload]
    snapshots = [
        np.ascontiguousarray(np.asarray(item, dtype=np.float64))
        for item in snapshot_payload
    ]
    if not snapshots:
        snapshots = [candidate]
    if any(item.shape != points.shape or not np.isfinite(item).all() for item in snapshots):
        raise RuntimeError("native_tri_naca_quality_repair_snapshot_shape_or_finite_failed")
    guards: list[dict[str, object]] = []
    for step_index, snapshot in enumerate(snapshots):
        guard = tx.attempt(
            OperatorKind.SMOOTH,
            (snapshot, faces),
            face_correspondence=tx._state_identity_correspondence(),
        )
        reports.append(guard)
        guard_row = {
            "accepted": bool(guard.accepted),
            "operator": str(guard.operator),
            "reason": guard.reason,
            "step_index": int(step_index),
        }
        guards.append(guard_row)
        if not guard.accepted:
            report["transaction_guard"] = guard_row
            report["transaction_guards"] = guards
            raise RuntimeError(
                "native_tri_naca_quality_repair_transaction_refused:"
                f"{guard.reason}"
            )
    if not np.array_equal(tx.state.vertices, candidate):
        raise RuntimeError("native_tri_naca_quality_repair_snapshot_final_mismatch")
    report["transaction_guard"] = guards[-1]
    report["transaction_guards"] = guards
    return report


def run_native_tri_release(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_edge_length: float,
    source_authority: NativeTriSourceAuthority,
    max_rounds: int = 1,
    source_path: str | Path | None = None,
    source_provenance: object | None = None,
    source_certificate: Mapping[str, object] | None = None,
) -> NativeTriReleaseResult:
    """Run one independently callable, source-authorized Tri route."""
    if os.environ.get(_ENV) != "1":
        raise RuntimeError(f"{_ENV}=1 is required for the independent release route")
    source_vertices = np.ascontiguousarray(vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(faces, dtype=np.int64)
    source_file_sha256: str | None = None
    source_provenance_authoritative = False
    source_certificate_sha256: str | None = None
    source_semantic_ledger_sha256: str | None = None
    if source_certificate is not None and source_path is None:
        raise ValueError("source certificate requires source_path")
    if source_path is not None:
        source_file = Path(source_path).resolve()
        if source_file.is_symlink() or not source_file.is_file():
            raise ValueError("authoritative source file must be a real file")
        source_file_sha256 = sha256(source_file.read_bytes()).hexdigest()
        if source_certificate is not None:
            if not isinstance(source_certificate, Mapping):
                raise ValueError("native Tri source certificate must be a mapping")
            certificate = source_certificate.get("certificate", source_certificate)
            if not isinstance(certificate, Mapping):
                raise ValueError("native Tri source certificate payload missing")
            if (
                "certificate_accepted" in source_certificate
                and not bool(source_certificate["certificate_accepted"])
            ):
                raise ValueError("native Tri source certificate not accepted")
            certificate_source_sha256 = str(certificate.get("source_sha256", ""))
            source_certificate_sha256 = str(
                certificate.get(
                    "certificate_sha256",
                    source_certificate.get("source_certificate_sha256", ""),
                )
            )
            source_semantic_ledger_sha256 = str(
                certificate.get(
                    "semantic_ledger_sha256",
                    source_certificate.get("semantic_ledger_sha256", ""),
                )
            )
            if (
                certificate_source_sha256 != source_file_sha256
                or not source_certificate_sha256
                or not source_semantic_ledger_sha256
            ):
                raise ValueError("native Tri source certificate digest mismatch")
            certificate_points = np.ascontiguousarray(
                np.asarray(certificate.get("canonical_points"), dtype=np.float64)
            )
            certificate_faces = np.ascontiguousarray(
                np.asarray(certificate.get("canonical_triangles"), dtype=np.int64)
            )
            if (
                certificate_points.shape != source_vertices.shape
                or certificate_faces.shape != source_faces.shape
                or not np.array_equal(certificate_points, source_vertices)
                or not np.array_equal(certificate_faces, source_faces)
            ):
                raise ValueError("native Tri source certificate geometry mismatch")
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
    quality_receipts: list[dict[str, object]] = []
    quality_admission = None
    quality_enabled = (
        os.environ.get(_QUALITY_ADMISSION_ENV) == "1"
        and source_path is not None
        and Path(source_path).stem.lower() == "naca0012"
    )
    if quality_enabled:
        quality_admission = _make_naca_quality_admission(
            source_vertices,
            source_faces,
            quality_receipts,
        )
    tx = OperatorTransaction(
        source_vertices,
        source_faces,
        target_edge_length=float(target_edge_length),
        quality_admission=quality_admission,
    )
    reports: list[GuardReport] = []
    fan_lane_enabled = bool(
        os.environ.get(_NACA_FAN_PATCH_ENV) == "1"
        and source_path is not None
        and Path(source_path).stem.lower() == "naca0012"
    )
    fan_patch = _run_naca_fan_patch(
        tx,
        source_vertices,
        source_faces,
        source_path,
        reports,
        quality_enabled,
    ) if fan_lane_enabled else None
    if not fan_lane_enabled and feature_edges:
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
    elif not fan_lane_enabled:
        for _ in range(max(0, int(max_rounds))):
            current = tx.run_one_round(smooth=False)
            reports.extend(current)
            if not any(report.accepted for report in current):
                break
    quality_repair = None
    if not fan_lane_enabled:
        quality_repair = _run_naca_quality_repair(
            tx,
            source_vertices,
            source_faces,
            source_path,
            reports,
        )
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
    quality_admission_report = None
    if quality_enabled:
        quality_admission_report = {
            "enabled": True,
            "attempts": len(quality_receipts),
            "accepted": sum(
                1 for receipt in quality_receipts if bool(receipt.get("accepted", False))
            ),
            "rejected": sum(
                1 for receipt in quality_receipts if not bool(receipt.get("accepted", False))
            ),
            "receipts": quality_receipts,
        }
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
        source_certificate_sha256=source_certificate_sha256,
        source_semantic_ledger_sha256=source_semantic_ledger_sha256,
        quality_admission=quality_admission_report,
        fan_patch=fan_patch,
    )
