"""Build C++ BRepFrontEvidence from the native CAD provenance sidecar."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from core.analyzer.readers.step import CadNativeTriangulation


def build_brep_front_evidence(
    cad: CadNativeTriangulation,
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Emit deterministic BRepFrontEvidence without changing legacy arrays."""

    provenance = cad.provenance
    if len(source_digest) != 64:
        raise ValueError("source_digest must be a 64-character digest")
    if not (
        provenance.face_ordinals_authoritative
        and provenance.face_orientation_authoritative
        and provenance.seam_connectivity_authoritative
    ):
        raise ValueError("CAD face/orientation/seam authority is incomplete")
    if cad.faces.ndim != 2 or cad.faces.shape[1] != 3:
        raise ValueError("CAD legacy faces must be a triangle stream")
    if provenance.oriented_canonical_faces.shape != cad.faces.shape:
        raise ValueError("canonical face stream shape mismatch")

    triangles: list[dict[str, Any]] = []
    edge_faces: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
    edge_triangles: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
    for triangle_id, (raw, canonical) in enumerate(
        zip(cad.faces.tolist(), provenance.oriented_canonical_faces.tolist(), strict=True)
    ):
        face_id = int(provenance.triangle_face_ordinals[triangle_id])
        triangles.append(
            {
                "triangle_id": triangle_id,
                "brep_face_id": face_id,
                "canonical_vertices": [int(value) for value in canonical],
                "raw_vertices": [int(value) for value in raw],
                "orientation_reversed": bool(provenance.triangle_orientation_reversed[triangle_id]),
            }
        )
        for index in range(3):
            key = tuple(sorted((int(canonical[index]), int(canonical[(index + 1) % 3]))))
            edge_faces[key].add(face_id)
            edge_triangles[key].add(triangle_id)

    edges = []
    for edge_id, key in enumerate(sorted(edge_faces)):
        edges.append(
            {
                "brep_edge_id": edge_id,
                "owner_face_id": min(edge_faces[key]),
                "canonical_endpoints": [key[0], key[1]],
                "incident_faces": sorted(edge_faces[key]),
                "incident_triangles": sorted(edge_triangles[key]),
            }
        )
    return {
        "schema": "BRepFrontEvidence/v1",
        "source_digest": source_digest,
        "triangles": triangles,
        "edges": edges,
        "authority": {
            "face_ordinals": True,
            "orientation": True,
            "seam_connectivity": True,
            "physical_groups": bool(provenance.physical_groups_authoritative),
            "runtime_route": "default_off",
        },
        "source_metadata": {
            "face_count": provenance.face_count,
            "triangle_count": int(cad.faces.shape[0]),
            "face_ordinal_digest": provenance.ordered_face_ordinal_sha256,
            "orientation_digest": provenance.ordered_orientation_sha256,
            "seam_digest": provenance.seam_connectivity_sha256,
            "xde_metadata_digest": provenance.xde_metadata_sha256,
        },
    }
