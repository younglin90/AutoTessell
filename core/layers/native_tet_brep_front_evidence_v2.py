"""Build actual B-Rep edge evidence from CAD-authoritative provenance."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Any, Mapping

import numpy as np

from core.analyzer.readers.step import CadNativeTriangulation


def _array_digest(values: np.ndarray, dtype: str) -> str:
    return hashlib.sha256(np.asarray(values, dtype=dtype).tobytes()).hexdigest()


def build_brep_front_evidence_v2(
    cad: CadNativeTriangulation,
    *,
    source_digest: str,
    owner_face_by_edge: Mapping[int, int],
) -> dict[str, Any]:
    """Emit actual B-Rep edge identity and triangle incidence without routing it."""

    provenance = cad.provenance
    if len(source_digest) != 64:
        raise ValueError("source_digest must be a 64-character digest")
    if not (
        provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    ):
        raise ValueError("CAD face/orientation/seam authority is incomplete")
    edge_ids = provenance.triangle_brep_edge_ids
    if edge_ids is None or edge_ids.shape != cad.faces.shape:
        raise ValueError("actual B-Rep triangle-edge provenance is missing")
    segment_ids = provenance.triangle_brep_edge_segment_ids
    segment_parameters = provenance.triangle_brep_edge_segment_parameters
    if segment_ids is None or segment_parameters is None:
        raise ValueError("actual B-Rep edge segment provenance is missing")
    if segment_ids.shape != cad.faces.shape or segment_parameters.shape != cad.faces.shape + (2,):
        raise ValueError("actual B-Rep edge segment provenance shape mismatch")
    if cad.faces.ndim != 2 or cad.faces.shape[1] != 3:
        raise ValueError("CAD legacy faces must be a triangle stream")
    if provenance.oriented_canonical_faces.shape != cad.faces.shape:
        raise ValueError("canonical face stream shape mismatch")
    if provenance.canonical_vertex_source_ids.ndim != 1:
        raise ValueError("canonical vertex source map is invalid")

    canonical_positions = np.asarray(
        cad.vertices[provenance.canonical_vertex_source_ids], dtype="<f8"
    )
    triangles: list[dict[str, Any]] = []
    edge_endpoints: dict[int, tuple[int, int]] = {}
    edge_segments: defaultdict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    edge_faces: defaultdict[int, set[int]] = defaultdict(set)
    edge_triangles: defaultdict[int, set[int]] = defaultdict(set)
    edge_triangles_by_face: defaultdict[int, defaultdict[int, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )

    for triangle_id, (raw, canonical, mapped, mapped_segment_ids, mapped_parameters) in enumerate(
        zip(
            cad.faces.tolist(),
            provenance.oriented_canonical_faces.tolist(),
            edge_ids.tolist(),
            segment_ids.tolist(),
            segment_parameters.tolist(),
            strict=True,
        )
    ):
        face_id = int(provenance.triangle_face_ordinals[triangle_id])
        triangles.append(
            {
                "triangle_id": triangle_id,
                "brep_face_id": face_id,
                "canonical_vertices": [int(value) for value in canonical],
                "raw_vertices": [int(value) for value in raw],
                "orientation_reversed": bool(
                    provenance.triangle_orientation_reversed[triangle_id]
                ),
                "brep_edge_ids": [int(value) for value in mapped],
                "brep_edge_segment_ids": [int(value) for value in mapped_segment_ids],
                "brep_edge_segment_parameters": [[float(value) for value in pair] for pair in mapped_parameters],
            }
        )
        for slot, value in enumerate(mapped):
            edge_id = int(value)
            segment_id = int(mapped_segment_ids[slot])
            t0, t1 = (float(value) for value in mapped_parameters[slot])
            if edge_id < 0:
                if segment_id != -1 or not (np.isnan(t0) and np.isnan(t1)):
                    raise ValueError("triangulation diagonal carries edge segment data")
                continue
            if segment_id < 0 or not np.isfinite(t0) or not np.isfinite(t1) or not (0.0 <= t0 <= 1.0) or not (0.0 <= t1 <= 1.0) or t0 == t1:
                raise ValueError("actual B-Rep edge segment parameter is invalid")
            prior_segment = edge_segments[edge_id].get(segment_id)
            if prior_segment is not None and prior_segment != (t0, t1):
                raise ValueError("actual B-Rep edge segment has inconsistent parameters")
            edge_segments[edge_id][segment_id] = (t0, t1)
            endpoints = tuple(
                sorted(
                    (
                        int(provenance.seam_vertex_ids[int(raw[slot])]),
                        int(provenance.seam_vertex_ids[int(raw[(slot + 1) % 3])]),
                    )
                )
            )
            prior = edge_endpoints.setdefault(edge_id, endpoints)
            if prior != endpoints:
                raise ValueError("actual B-Rep edge has inconsistent canonical endpoints")
            edge_faces[edge_id].add(face_id)
            edge_triangles[edge_id].add(triangle_id)
            edge_triangles_by_face[edge_id][face_id].add(triangle_id)

    edges: list[dict[str, Any]] = []
    for edge_id in sorted(edge_endpoints):
        if edge_id not in owner_face_by_edge:
            raise ValueError(f"explicit owner is missing for B-Rep edge {edge_id}")
        owner = int(owner_face_by_edge[edge_id])
        incident_faces = sorted(edge_faces[edge_id])
        if owner not in incident_faces:
            raise ValueError(f"explicit owner is not incident for B-Rep edge {edge_id}")
        incident_by_face = [
            {
                "face_id": face_id,
                "triangle_ids": sorted(edge_triangles_by_face[edge_id][face_id]),
            }
            for face_id in incident_faces
        ]
        edges.append(
            {
                "brep_edge_id": edge_id,
                "is_actual_brep_edge": True,
                "owner_face_id": owner,
                "canonical_endpoints": list(edge_endpoints[edge_id]),
                "incident_faces": incident_faces,
                "incident_triangles": sorted(edge_triangles[edge_id]),
                "incident_triangles_by_face": incident_by_face,
                "segments": [
                    {"segment_id": segment_id, "t0": parameters[0], "t1": parameters[1]}
                    for segment_id, parameters in sorted(edge_segments[edge_id].items())
                ],
            }
        )

    direction_records: list[dict[str, Any]] = []
    for sector_id, source_record in enumerate(provenance.brep_edge_face_direction_records or ()):
        record = dict(source_record)
        record["sector_id"] = sector_id
        surface_du = np.asarray(record["surface_du"], dtype=np.float64)
        surface_dv = np.asarray(record["surface_dv"], dtype=np.float64)
        normal = np.cross(surface_du, surface_dv)
        normal_norm = float(np.linalg.norm(normal))
        if normal_norm <= 1.0e-14:
            raise ValueError("B-Rep surface derivative has zero normal")
        record["face_normal"] = (normal / normal_norm * float(record["face_orientation_sign"])).tolist()
        record["domain_side"] = record["mesh_domain_side"]
        record["source_digest"] = source_digest
        record["domain_side_authority"] = bool(record["domain_side_authoritative"])
        direction_records.append(record)

    return {
        "schema": "BRepFrontEvidence/v2",
        "source_digest": source_digest,
        "canonical_positions": canonical_positions.tolist(),
        "canonical_positions_digest": _array_digest(canonical_positions, "<f8"),
        "face_ordinal_digest": provenance.ordered_face_ordinal_sha256,
        "orientation_digest": provenance.ordered_orientation_sha256,
        "seam_digest": provenance.seam_connectivity_sha256,
        "triangles": triangles,
        "edges": edges,
        "direction_records": direction_records,
        "direction_authority": bool(direction_records) and all(
            record["domain_side_authority"]
            and record["trimmed_interior_status"] == "one_side_certified"
            for record in direction_records
        ),
        "authority": {
            "face_ordinals": bool(provenance.face_ordinals_authoritative),
            "orientation": bool(provenance.face_orientation_authoritative),
            "seam_connectivity": bool(provenance.seam_connectivity_authoritative),
            "physical_groups": bool(provenance.physical_groups_authoritative),
            "runtime_route": "default_off",
        },
        "non_manifold_edge_count": 0,
        "missing_edge_polygon_count": 0,
        "source_metadata": {
            "face_count": provenance.face_count,
            "triangle_count": int(cad.faces.shape[0]),
            "topological_edge_count": provenance.topological_edge_count,
            "xde_metadata_digest": provenance.xde_metadata_sha256,
        },
    }
