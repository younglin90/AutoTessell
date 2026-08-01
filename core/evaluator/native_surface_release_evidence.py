"""Measured source/output authority for independent fixed-pair surfaces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.evaluator.strict_surface_topology import audit_strict_surface_topology


def _sha(value: object) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _combine(*values: object) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _canonical_faces(faces: np.ndarray) -> tuple[tuple[int, int, int], ...]:
    return tuple(sorted(tuple(sorted(int(x) for x in row)) for row in faces))


def certify_fixed_pair_surface_output(
    product_result: Any,
    writer_result: Any,
    source_path: Path,
    source_vertices: object,
    source_triangles: object,
) -> dict[str, object]:
    """Certify an admitted fixed-pair artifact; no claims are inferred."""
    source_file = Path(source_path)
    source_sha = (
        hashlib.sha256(source_file.read_bytes()).hexdigest()
        if source_file.is_file() and not source_file.is_symlink()
        else None
    )
    base = {"authoritative": False, "source_sha256": source_sha}
    product = getattr(product_result, "product", None)
    if source_sha is None or product is None or not getattr(product_result, "accepted", False):
        return base | {"rejection_reason": "surface_authority_incomplete"}
    if not getattr(writer_result, "written", False) or not getattr(
        writer_result, "readback_verified", False
    ):
        return base | {"rejection_reason": "writer_readback_unverified"}
    source = np.asarray(source_vertices, dtype=np.float64)
    source_faces = np.asarray(source_triangles, dtype=np.int64)
    vertices = np.asarray(product.vertices, dtype=np.float64)
    residual = np.asarray(getattr(product, "triangles", ()), dtype=np.int64)
    expanded = [tuple(map(int, row)) for row in residual]
    for quad in np.asarray(getattr(product, "quads", ()), dtype=np.int64):
        a, b, c, d = map(int, quad)
        expanded.extend(((a, b, c), (a, c, d)))
    output_faces = np.asarray(expanded, dtype=np.int64)
    surface = audit_strict_surface_topology(vertices, output_faces)
    residual_indices = np.asarray(getattr(product, "triangle_source_indices", ()), dtype=np.int64)
    pair_indices = np.asarray(getattr(product, "quad_source_pairs", ()), dtype=np.int64)
    provenance_indices = tuple(int(x) for x in residual_indices.tolist()) + tuple(
        int(x) for row in pair_indices.tolist() for x in row
    )
    provenance = sorted(provenance_indices) == list(range(len(source_faces)))
    shape = bool(surface.valid and np.array_equal(vertices, source))
    feature_hash = getattr(product, "feature_hash", None)
    patch_hash = getattr(product, "source_patch_hash", None)
    group_hash = getattr(product, "source_physical_group_hash", None)
    hashes_valid = all(
        isinstance(x, str) and len(x) == 64 for x in (feature_hash, patch_hash, group_hash)
    )
    groups = tuple(getattr(product, "triangle_physical_groups", ())) + tuple(
        getattr(product, "quad_physical_groups", ())
    )
    groups_valid = bool(groups) and all(isinstance(x, str) and x.strip() for x in groups)
    authority = bool(shape and provenance and hashes_valid and groups_valid)
    source_shape = _combine(_sha(source), _sha(source_faces))
    output_shape = _combine(_sha(vertices), _sha(output_faces))
    return {
        "status": "measured_authoritative_fixed_pair_surface"
        if authority
        else "reject_fixed_pair_surface_authority",
        "authoritative": authority,
        "source_sha256": source_sha,
        "source_shape_sha256": source_shape,
        "output_shape_sha256": output_shape,
        "feature_sha256": feature_hash,
        "patch_sha256": patch_hash,
        "physical_group_sha256": group_hash,
        "provenance_sha256": _combine(provenance_indices, pair_indices.tolist()),
        "shape_preserved": shape,
        "source_vertices_preserved": shape,
        "source_faces_preserved": provenance,
        "source_face_provenance": provenance,
        "feature_preserved": hashes_valid,
        "patch_preserved": hashes_valid,
        "physical_groups_preserved": groups_valid,
        "component_bijection": provenance,
        "provenance_complete": provenance,
        "surface_topology": surface.as_dict(),
        "artifact_sha256": surface.artifact_sha256,
        "rejection_reason": None if authority else "fixed_pair_surface_authority_incomplete",
    }


__all__ = ["certify_fixed_pair_surface_output"]
