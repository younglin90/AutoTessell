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



_HEX_POLYMESH_FILES: tuple[str, ...] = ("points", "faces", "owner", "neighbour", "boundary")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def native_hex_polymesh_digest(
    poly_dir: str | Path,
) -> tuple[str, dict[str, str]]:
    """Return a canonical digest for the five pre-BL polyMesh files."""
    root = Path(poly_dir)
    file_hashes: dict[str, str] = {}
    for name in _HEX_POLYMESH_FILES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"native Hex polyMesh file missing: {path}")
        file_hashes[name] = _sha256_file(path)
    return _canonical_sha256({"files": file_hashes}), file_hashes


def _source_binding_digest(
    evidence: HexMeasuredSourceBinding,
    writer_order_source_face_sha256: str,
    ingress_certificate_sha256: str | None = None,
    semantic_ledger_sha256: str | None = None,
    provisioning_manifest_sha256: str | None = None,
) -> str:
    return _canonical_sha256(
        {
            "contract": evidence.contract,
            "source_file_sha256": evidence.source_file_sha256,
            "source_brep_authoritative": bool(evidence.source_brep_authoritative),
            "physical_groups_authoritative": bool(
                evidence.physical_groups_authoritative
            ),
            "output_boundary_face_count": int(evidence.output_boundary_face_count),
            "output_to_source_face_sha256": evidence.output_to_source_face_sha256,
            "output_physical_group_sha256": evidence.output_physical_group_sha256,
            "writer_order_source_face_sha256": writer_order_source_face_sha256,
            "ingress_certificate_sha256": ingress_certificate_sha256,
            "semantic_ledger_sha256": semantic_ledger_sha256,
            "provisioning_manifest_sha256": provisioning_manifest_sha256,
            "max_source_plane_distance": evidence.max_source_plane_distance,
            "tolerance": evidence.tolerance,
        }
    )


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


def write_hex_source_face_map(
    case_dir: str | Path,
    hexes: np.ndarray,
    evidence: HexMeasuredSourceBinding,
    *,
    ingress_certificate: dict[str, object] | None = None,
) -> dict[str, object]:
    """Persist the base writer-order face map for a later BL writer.

    The map is keyed by the actual baseline polyMesh face index. It is a
    lineage handoff, not a geometric reclassification: a later boundary-layer
    writer may only reuse these source owners through its own explicit output
    order records.
    """
    if not evidence.strict_binding_complete:
        return {"accepted": False, "reason": "source_binding_not_strict"}
    try:
        from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels

        root = Path(case_dir) / "constant" / "polyMesh"
        written_faces = parse_foam_faces(root / "faces")
        internal_count = len(parse_foam_labels(root / "neighbour"))
        boundary = extract_hex_boundary_faces(np.asarray(hexes, dtype=np.int64))
        mapping = tuple(int(value) for value in evidence.output_face_to_source_face)
        if len(mapping) != len(boundary):
            return {
                "accepted": False,
                "reason": "source_binding_boundary_count_mismatch",
            }
        by_key = {
            tuple(sorted(int(value) for value in face)): mapping[index]
            for index, face in enumerate(boundary)
        }
        records: list[dict[str, int]] = []
        for mesh_face, face in enumerate(written_faces[internal_count:], internal_count):
            source_face = by_key.get(tuple(sorted(int(value) for value in face)))
            if source_face is None:
                return {
                    "accepted": False,
                    "reason": "baseline_writer_face_not_bound",
                }
            records.append({
                "writer_order": len(records),
                "source_mesh_face": int(mesh_face),
                "source_face": int(source_face),
            })
        if len(records) != len(boundary):
            return {
                "accepted": False,
                "reason": "baseline_writer_boundary_count_mismatch",
            }
        writer_mapping = [int(row["source_face"]) for row in records]
        writer_order_source_face_sha256 = _array_hash(
            np.asarray(writer_mapping, dtype=np.int64)
        )
        ingress_certificate_sha256: str | None = None
        semantic_ledger_sha256: str | None = None
        provisioning_manifest_sha256: str | None = None
        ingress_fields: dict[str, object] = {}
        if ingress_certificate is not None:
            if ingress_certificate.get("accepted") is not True:
                return {
                    "accepted": False,
                    "reason": "ingress_certificate_not_authoritative",
                }
            ingress_certificate_sha256 = str(
                ingress_certificate.get("certificate_sha256", "")
            )
            if len(ingress_certificate_sha256) != 64:
                return {
                    "accepted": False,
                    "reason": "ingress_certificate_digest_missing",
                }
            for key in (
                "face_stream_sha256",
                "triangulation_stream_sha256",
                "semantic_ledger_sha256",
                "occt_provisioning_manifest_sha256",
                "occt_version",
                "occt_abi",
            ):
                value = ingress_certificate.get(key)
                if value is None or not str(value):
                    return {
                        "accepted": False,
                        "reason": f"ingress_certificate_field_missing:{key}",
                    }
                ingress_fields[f"ingress_{key}"] = str(value)
            ingress_fields["ingress_certificate_sha256"] = ingress_certificate_sha256
            semantic_ledger_sha256 = str(
                ingress_certificate.get("semantic_ledger_sha256", "")
            )
            ingress_fields["ingress_semantic_ledger_sha256"] = semantic_ledger_sha256
            provisioning_manifest_sha256 = str(
                ingress_certificate.get("occt_provisioning_manifest_sha256", "")
            )
            if len(provisioning_manifest_sha256) != 64:
                return {
                    "accepted": False,
                    "reason": "provisioning_manifest_digest_missing",
                }
            ingress_fields["ingress_occt_provisioning_manifest_sha256"] = (
                provisioning_manifest_sha256
            )
        baseline_sha256, baseline_file_sha256 = native_hex_polymesh_digest(root)
        source_binding_sha256 = _source_binding_digest(
            evidence,
            writer_order_source_face_sha256,
            ingress_certificate_sha256,
            semantic_ledger_sha256,
            provisioning_manifest_sha256,
        )
        payload = {
            "schema": (
                "autotessell/native-hex-source-face-map/v3"
                if ingress_certificate_sha256 is not None
                else "autotessell/native-hex-source-face-map/v2"
            ),
            "baseline_polymesh_sha256": baseline_sha256,
            "baseline_file_sha256": baseline_file_sha256,
            "source_binding_sha256": source_binding_sha256,
            "source_face_count": int(max(mapping) + 1) if mapping else 0,
            "records": records,
            "output_to_source_face_sha256": _array_hash(
                np.asarray(mapping, dtype=np.int64)
            ),
            "writer_order_source_face_sha256": writer_order_source_face_sha256,
            **ingress_fields,
        }
        payload["map_sha256"] = _canonical_sha256(payload)
        path = Path(case_dir) / "native_hex_source_face_map.json"
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + chr(10)
        )
        return {
            "accepted": True,
            "path": str(path),
            "record_count": len(records),
            "source_face_count": payload["source_face_count"],
            "baseline_polymesh_sha256": baseline_sha256,
            "source_binding_sha256": source_binding_sha256,
            "map_sha256": payload["map_sha256"],
            "ingress_certificate_sha256": ingress_certificate_sha256,
            "semantic_ledger_sha256": semantic_ledger_sha256,
            "provisioning_manifest_sha256": provisioning_manifest_sha256,
        }
    except Exception as exc:
        return {
            "accepted": False,
            "reason": f"source_face_map_write_failed:{type(exc).__name__}",
        }



def validate_native_hex_source_face_map(
    case_dir: str | Path,
) -> dict[str, object]:
    """Validate a v2 source map against the current pre-BL polyMesh."""
    path = Path(case_dir) / "native_hex_source_face_map.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("source_map_root_invalid")
        schema = payload.get("schema")
        if schema not in (
            "autotessell/native-hex-source-face-map/v2",
            "autotessell/native-hex-source-face-map/v3",
        ):
            raise ValueError("source_map_schema_unsupported")
        if schema == "autotessell/native-hex-source-face-map/v3":
            for key in (
                "ingress_certificate_sha256",
                "ingress_face_stream_sha256",
                "ingress_triangulation_stream_sha256",
                "ingress_semantic_ledger_sha256",
                "ingress_occt_provisioning_manifest_sha256",
                "ingress_occt_version",
                "ingress_occt_abi",
            ):
                value = payload.get(key)
                if not isinstance(value, str) or not value:
                    raise ValueError(f"source_map_ingress_field_missing:{key}")
            if len(str(payload["ingress_certificate_sha256"])) != 64:
                raise ValueError("source_map_ingress_digest_invalid")
            if len(str(payload["ingress_semantic_ledger_sha256"])) != 64:
                raise ValueError("source_map_semantic_ledger_digest_invalid")
            if len(str(payload["ingress_occt_provisioning_manifest_sha256"])) != 64:
                raise ValueError("source_map_provisioning_manifest_digest_invalid")
        baseline_sha256, baseline_file_sha256 = native_hex_polymesh_digest(
            Path(case_dir) / "constant" / "polyMesh"
        )
        if payload.get("baseline_polymesh_sha256") != baseline_sha256:
            raise ValueError("source_map_baseline_digest_mismatch")
        if payload.get("baseline_file_sha256") != baseline_file_sha256:
            raise ValueError("source_map_baseline_file_digest_mismatch")
        supplied_map_sha256 = payload.get("map_sha256")
        if not isinstance(supplied_map_sha256, str) or len(supplied_map_sha256) != 64:
            raise ValueError("source_map_digest_missing")
        unsigned_payload = dict(payload)
        unsigned_payload.pop("map_sha256", None)
        if supplied_map_sha256 != _canonical_sha256(unsigned_payload):
            raise ValueError("source_map_digest_mismatch")

        from core.utils.polymesh_reader import parse_foam_faces, parse_foam_labels

        root = Path(case_dir) / "constant" / "polyMesh"
        written_faces = parse_foam_faces(root / "faces")
        internal_count = len(parse_foam_labels(root / "neighbour"))
        boundary_count = len(written_faces) - internal_count
        records = payload.get("records")
        if not isinstance(records, list) or len(records) != boundary_count:
            raise ValueError("source_map_boundary_count_mismatch")
        source_face_count = int(payload.get("source_face_count", -1))
        if source_face_count <= 0:
            raise ValueError("source_map_source_face_count_invalid")
        writer_mapping: list[int] = []
        seen_mesh_faces: set[int] = set()
        for index, row in enumerate(records):
            if not isinstance(row, dict):
                raise ValueError("source_map_record_invalid")
            if int(row.get("writer_order", -1)) != index:
                raise ValueError("source_map_writer_order_invalid")
            source_mesh_face = int(row.get("source_mesh_face", -1))
            if source_mesh_face != internal_count + index:
                raise ValueError("source_map_mesh_face_order_invalid")
            if source_mesh_face in seen_mesh_faces:
                raise ValueError("source_map_mesh_face_duplicate")
            seen_mesh_faces.add(source_mesh_face)
            source_face = int(row.get("source_face", -1))
            if source_face < 0 or source_face >= source_face_count:
                raise ValueError("source_map_source_face_invalid")
            writer_mapping.append(source_face)
        if set(writer_mapping) != set(range(source_face_count)):
            raise ValueError("source_map_source_face_coverage_incomplete")
        writer_hash = _array_hash(np.asarray(writer_mapping, dtype=np.int64))
        if payload.get("writer_order_source_face_sha256") != writer_hash:
            raise ValueError("source_map_writer_mapping_digest_mismatch")
        source_binding_sha256 = payload.get("source_binding_sha256")
        if not isinstance(source_binding_sha256, str) or len(source_binding_sha256) != 64:
            raise ValueError("source_map_binding_digest_missing")
        return {
            "accepted": True,
            "path": str(path),
            "schema": schema,
            "records": records,
            "source_face_count": source_face_count,
            "baseline_polymesh_sha256": baseline_sha256,
            "baseline_file_sha256": baseline_file_sha256,
            "source_binding_sha256": source_binding_sha256,
            "map_sha256": supplied_map_sha256,
            "writer_order_source_face_sha256": writer_hash,
            "ingress_certificate_sha256": payload.get(
                "ingress_certificate_sha256"
            ),
            "semantic_ledger_sha256": payload.get(
                "ingress_semantic_ledger_sha256"
            ),
            "provisioning_manifest_sha256": payload.get(
                "ingress_occt_provisioning_manifest_sha256"
            ),
        }
    except Exception as exc:
        return {
            "accepted": False,
            "path": str(path),
            "reason": f"{type(exc).__name__}:{exc}",
        }



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
