"""Fail-closed runtime entry point for the native-tri L2 route.

The local operator engine does not yet have a source-envelope and per-face
provenance certificate for topology-changing edits.  This entry point makes
that limitation explicit: an opt-in request is reported, but returns the
unchanged source until the certificate exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import numpy as np


def _array_hash(values: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(values)
    digest = sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class NativeTriL2RouteResult:
    """Machine-readable fail-closed result for an explicit native-tri request."""

    accepted: bool
    reason: str
    vertices: np.ndarray
    faces: np.ndarray
    source_vertices_hash: str
    source_faces_hash: str
    output_vertices_hash: str
    output_faces_hash: str
    provenance_hash: str
    source_envelope_preserved: bool
    topology_preserved: bool
    provenance_preserved: bool
    target_faces_requested: int | None
    target_faces_actual: int
    target_faces_absolute_error: int | None
    target_faces_relative_error: float | None
    boundary_layers_requested: int
    boundary_layers_actual: int
    layer_budget_reserved: int


def run_native_tri_l2_route(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_faces: int | None,
    boundary_layers: int = 0,
) -> NativeTriL2RouteResult:
    """Return unchanged source until a hard edit certificate is implemented.

    Keeping the route explicit permits the production pipeline to expose a
    truthful native-tri result today without admitting an unproven surface
    edit.  It intentionally performs no split, collapse, flip, smoothing, or
    layer generation.
    """
    source_vertices = np.asarray(vertices, dtype=np.float64)
    source_faces = np.asarray(faces, dtype=np.int64)
    output_vertices = source_vertices.copy()
    output_faces = source_faces.copy()
    source_vertices_hash = _array_hash(source_vertices)
    source_faces_hash = _array_hash(source_faces)
    output_vertices_hash = _array_hash(output_vertices)
    output_faces_hash = _array_hash(output_faces)
    source_preserved = (
        source_vertices_hash == output_vertices_hash
        and source_faces_hash == output_faces_hash
    )
    requested = int(target_faces) if target_faces is not None and target_faces > 0 else None
    actual = int(len(output_faces))
    absolute_error = None if requested is None else abs(actual - requested)
    relative_error = None if requested is None else absolute_error / requested
    requested_layers = max(0, int(boundary_layers))
    reason = (
        "boundary_layers_unsupported_by_surface_route"
        if requested_layers > 0
        else "source_contract_unavailable"
    )
    return NativeTriL2RouteResult(
        accepted=False,
        reason=reason,
        vertices=output_vertices,
        faces=output_faces,
        source_vertices_hash=source_vertices_hash,
        source_faces_hash=source_faces_hash,
        output_vertices_hash=output_vertices_hash,
        output_faces_hash=output_faces_hash,
        provenance_hash=source_faces_hash,
        source_envelope_preserved=source_preserved,
        topology_preserved=source_preserved,
        provenance_preserved=source_preserved,
        target_faces_requested=requested,
        target_faces_actual=actual,
        target_faces_absolute_error=absolute_error,
        target_faces_relative_error=relative_error,
        boundary_layers_requested=requested_layers,
        boundary_layers_actual=0,
        layer_budget_reserved=0,
    )
