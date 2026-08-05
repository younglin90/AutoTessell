"""Measured source/output evidence adapter for the independent Native-Tri route."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import numpy as np

from core.analyzer import topology
from core.evaluator.strict_surface_topology import audit_strict_surface_topology

def _combine(*values: object) -> str:
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=True,separators=(",",":")).encode()).hexdigest()

def certify_native_tri_release_result(
    result: Any,
    source_path: Path,
    source_faces: object,
) -> dict[str, object]:
    source_file=Path(source_path)
    try:
        faces=np.asarray(source_faces,dtype=np.int64)
        output_faces=np.asarray(result.faces,dtype=np.int64)
        output_points=np.asarray(result.vertices,dtype=np.float64)
    except (TypeError,ValueError,AttributeError) as exc:
        return {"authoritative":False,"rejection_reason":f"arrays_invalid:{type(exc).__name__}"}
    raw_sha=hashlib.sha256(source_file.read_bytes()).hexdigest() if source_file.is_file() and not source_file.is_symlink() else None
    source_sha=getattr(result,"source_file_sha256",None)
    certificate_sha=getattr(result,"source_certificate_sha256",None)
    semantic_ledger_sha=getattr(result,"source_semantic_ledger_sha256",None)
    certificate_binding=bool(
        certificate_sha is None
        or (isinstance(certificate_sha,str) and certificate_sha.strip()
            and isinstance(semantic_ledger_sha,str) and semantic_ledger_sha.strip())
    )
    provenance=tuple(getattr(result,"source_face_provenance",()))
    face_provenance=bool(
        len(provenance)==len(output_faces)
        and all(isinstance(index,(int,np.integer)) and 0<=int(index)<len(faces) for index in provenance)
    )
    source_components=topology.num_connected_components(faces)
    output_components=topology.num_connected_components(output_faces)
    component_bijection=bool(source_components==output_components and source_components>0)
    surface=audit_strict_surface_topology(output_points,output_faces)
    shape_preserved=bool(getattr(result,"source_envelope_preserved",False))
    feature_preserved=bool(
        getattr(result,"feature_edges_total",0)==0
        or float(getattr(result,"feature_recall",0.0))==1.0
    )
    patch_preserved=bool(len(getattr(result,"output_patch_ids",()))==len(output_faces))
    groups=tuple(getattr(result,"output_physical_groups",()))
    physical_groups_preserved=bool(len(groups)==len(output_faces) and all(isinstance(group,str) and group.strip() for group in groups))
    provenance_complete=bool(face_provenance and component_bijection and getattr(result,"source_topology_valid",False) and getattr(result,"output_topology_valid",False))
    authoritative=bool(
        getattr(result,"accepted",False)
        and getattr(result,"independent_route",False)
        and getattr(result,"transaction_applied",False)
        and source_sha is not None and source_sha==raw_sha
        and getattr(result,"source_provenance_authoritative",False)
        and certificate_binding
        and surface.valid and shape_preserved and feature_preserved
        and patch_preserved and physical_groups_preserved and provenance_complete
    )
    return {
        "status":"measured_authoritative_native_tri_surface" if authoritative else "reject_native_tri_surface_authority",
        "authoritative":authoritative,
        "source_sha256":source_sha,
        "source_certificate_sha256":certificate_sha,
        "semantic_ledger_sha256":semantic_ledger_sha,
        "certificate_binding":certificate_binding,
        "source_shape_sha256":_combine(getattr(result,"source_vertices_sha256",None),getattr(result,"source_faces_sha256",None)),
        "output_shape_sha256":_combine(getattr(result,"output_vertices_sha256",None),getattr(result,"output_faces_sha256",None)),
        "feature_sha256":getattr(result,"source_feature_sha256",None),
        "patch_sha256":getattr(result,"source_patch_sha256",None),
        "physical_group_sha256":getattr(result,"source_physical_group_sha256",None),
        "provenance_sha256":_combine(tuple(provenance),getattr(result,"source_faces_sha256",None),getattr(result,"output_faces_sha256",None)),
        "shape_preserved":shape_preserved,
        "source_vertices_preserved":False,
        "source_faces_preserved":False,
        "source_face_provenance":face_provenance,
        "feature_preserved":feature_preserved,
        "patch_preserved":patch_preserved,
        "physical_groups_preserved":physical_groups_preserved,
        "component_bijection":component_bijection,
        "provenance_complete":provenance_complete,
        "surface_topology":surface.as_dict(),
        "rejection_reason":None if authoritative else "native_tri_surface_authority_incomplete",
    }

__all__=["certify_native_tri_release_result"]
