"""Default-OFF certified planar edge-flip candidate for native-tri.

This is one real local operation, not a general surface mesher.  It materializes
only an in-memory candidate after source boundary, declared feature, topology,
patch, and two-face region provenance checks pass.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from numbers import Integral
from typing import Sequence

import numpy as np

from .operator_loop import OperatorTransaction

_ENV = "AUTO_TESSELL_TRI_STRICT_PLANAR_FLIP_PRODUCT_L0"


def _hash(values: np.ndarray) -> str:
    digest = sha256()
    digest.update(str(values.dtype).encode("ascii"))
    digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
    digest.update(values.tobytes())
    return digest.hexdigest()


def _edges(faces: np.ndarray) -> Counter[tuple[int, int]]:
    return Counter(
        (min(int(a), int(b)), max(int(a), int(b)))
        for face in faces.tolist()
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    )


def _topology(faces: np.ndarray, vertex_count: int) -> tuple[tuple[tuple[int, int], ...], int, int]:
    counts = _edges(faces)
    boundary = tuple(sorted(edge for edge, count in counts.items() if count == 1))
    adjacency = [set() for _ in range(len(faces))]
    owners: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(faces.tolist()):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            owners.setdefault((min(int(a), int(b)), max(int(a), int(b))), []).append(face_index)
    for face_owners in owners.values():
        if len(face_owners) == 2:
            first, second = face_owners
            adjacency[first].add(second)
            adjacency[second].add(first)
    unseen = set(range(len(faces)))
    components = 0
    while unseen:
        components += 1
        pending = [unseen.pop()]
        while pending:
            pending.extend(adjacency[pending.pop()].intersection(unseen))
            unseen.difference_update(pending)
    return boundary, components, vertex_count - len(counts) + len(faces)


def _patches(values: Sequence[int | str | None], count: int) -> tuple[int | str | None, ...] | None:
    if len(values) != count:
        return None
    result: list[int | str | None] = []
    for value in values:
        scalar = value.item() if isinstance(value, np.generic) else value
        if isinstance(scalar, bool) or not isinstance(scalar, (Integral, str, type(None))):
            return None
        result.append(int(scalar) if isinstance(scalar, Integral) else scalar)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipProduct:
    vertices: np.ndarray
    faces: np.ndarray
    patch_ids: tuple[int | str | None, ...]
    source_vertices_hash: str
    source_faces_hash: str
    face_region_provenance: tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipProductResult:
    accepted: bool
    status: str
    rejection_reason: str | None
    source_boundary_preserved: bool
    source_features_preserved: bool
    topology_preserved: bool
    provenance_preserved: bool
    independent_product_ready: bool
    product: StrictPlanarFlipProduct | None


def materialize_strict_planar_flip_product_l0(
    vertices: np.ndarray,
    faces: np.ndarray,
    edge: tuple[int, int],
    *,
    source_patch_ids: Sequence[int | str | None],
    source_feature_edges: Sequence[tuple[int, int]] = (),
) -> StrictPlanarFlipProductResult:
    """Run one actual flip only when its exact source-region certificate passes."""
    source_vertices = np.ascontiguousarray(vertices, dtype=np.float64)
    source_faces = np.ascontiguousarray(faces, dtype=np.int64)
    patches = _patches(source_patch_ids, len(source_faces))
    feature_edges = {tuple(sorted((int(a), int(b)))) for a, b in source_feature_edges}
    protected = tuple(sorted(edge))
    rejected = lambda status, reason: StrictPlanarFlipProductResult(False, status, reason, False, False, False, False, False, None)
    if patches is None:
        return rejected("reject_strict_planar_flip_patch_payload", "source_patch_payload_invalid")
    if protected in feature_edges:
        return rejected("reject_strict_planar_flip_feature", "source_feature_edge_protected")
    if os.environ.get(_ENV) != "1":
        return rejected("reject_strict_planar_flip_disabled", "strict_planar_flip_product_l0_disabled")
    source_edge_owners = [index for index, face in enumerate(source_faces.tolist()) if protected in {
        tuple(sorted((face[0], face[1]))), tuple(sorted((face[1], face[2]))), tuple(sorted((face[2], face[0])))}]
    if len(source_edge_owners) != 2 or patches[source_edge_owners[0]] != patches[source_edge_owners[1]]:
        return rejected("reject_strict_planar_flip_preflight", "flip_pair_or_patch_precondition_failed")
    transaction = OperatorTransaction(source_vertices, source_faces)
    report = transaction.flip_edge(protected)
    if not report.accepted:
        return rejected("reject_strict_planar_flip_operator", report.reason)
    candidate_vertices = transaction.state.vertices
    candidate_faces = transaction.state.faces
    source_boundary, source_components, source_euler = _topology(source_faces, len(source_vertices))
    candidate_boundary, candidate_components, candidate_euler = _topology(candidate_faces, len(candidate_vertices))
    boundary_ok = source_boundary == candidate_boundary
    topology_ok = source_components == candidate_components and source_euler == candidate_euler
    features_ok = feature_edges.issubset(set(_edges(candidate_faces)))
    vertices_ok = source_vertices.tobytes() == candidate_vertices.tobytes()
    provenance_ok = vertices_ok and boundary_ok and topology_ok and features_ok
    if not provenance_ok:
        return rejected("reject_strict_planar_flip_certificate", "source_region_certificate_failed")
    product = StrictPlanarFlipProduct(
        vertices=np.ascontiguousarray(candidate_vertices).copy(),
        faces=np.ascontiguousarray(candidate_faces).copy(),
        patch_ids=patches,
        source_vertices_hash=_hash(source_vertices),
        source_faces_hash=_hash(source_faces),
        face_region_provenance=(tuple(sorted(source_edge_owners)), tuple(sorted(source_edge_owners))),
    )
    product.vertices.setflags(write=False); product.faces.setflags(write=False)
    return StrictPlanarFlipProductResult(True, "pass_strict_planar_flip_candidate", None, True, True, True, True, False, product)

