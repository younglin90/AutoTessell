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

import numpy as np

from .operator_loop import OperatorTransaction
from .strict_planar_flip_source_l0 import StrictPlanarFlipSource

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


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipProduct:
    vertices: np.ndarray
    faces: np.ndarray
    patch_ids: tuple[int | str | None, ...]
    physical_groups: tuple[str, ...]
    source_sha256: str
    source_vertices_hash: str
    source_faces_hash: str
    source_physical_groups_hash: str
    face_region_provenance: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class StrictPlanarFlipProductResult:
    accepted: bool
    status: str
    rejection_reason: str | None
    source_boundary_preserved: bool
    source_features_preserved: bool
    topology_preserved: bool
    provenance_preserved: bool
    authority_preserved: bool
    independent_product_ready: bool
    product: StrictPlanarFlipProduct | None


def materialize_strict_planar_flip_product_l0(
    source: object,
    edge: tuple[int, int],
) -> StrictPlanarFlipProductResult:
    """Run one actual flip only when its exact source-region certificate passes."""
    def rejected(status: str, reason: str) -> StrictPlanarFlipProductResult:
        return StrictPlanarFlipProductResult(
            False, status, reason, False, False, False, False, False, False, None
        )

    if not isinstance(source, StrictPlanarFlipSource):
        return rejected(
            "reject_strict_planar_flip_source",
            "strict_planar_flip_source_locked_authority_required",
        )
    source_vertices = source.vertices
    source_faces = source.faces
    patches = source.patch_ids
    groups = source.physical_groups
    source_binding_ok = (
        source.contract == "strict_planar_flip_source_l0_test_authority"
        and source_vertices.dtype == np.dtype(np.float64)
        and source_faces.dtype == np.dtype(np.int64)
        and source_vertices.flags.c_contiguous
        and source_faces.flags.c_contiguous
        and not source_vertices.flags.writeable
        and not source_faces.flags.writeable
        and source_vertices.ndim == 2
        and source_vertices.shape[1] == 3
        and source_faces.ndim == 2
        and source_faces.shape[1] == 3
        and len(patches) == len(source_faces)
        and len(groups) == len(source_faces)
        and source.vertices_sha256 == _hash(source_vertices)
        and source.faces_sha256 == _hash(source_faces)
        and source.physical_groups_sha256 == sha256(repr(groups).encode("utf-8")).hexdigest()
    )
    if not source_binding_ok:
        return rejected(
            "reject_strict_planar_flip_source",
            "strict_planar_flip_source_binding_invalid",
        )
    feature_edges = set(source.feature_edges)
    protected = tuple(sorted(edge))
    if protected in feature_edges:
        return rejected("reject_strict_planar_flip_feature", "source_feature_edge_protected")
    if os.environ.get(_ENV) != "1":
        return rejected(
            "reject_strict_planar_flip_disabled", "strict_planar_flip_product_l0_disabled"
        )
    source_edge_owners = [
        index
        for index, face in enumerate(source_faces.tolist())
        if protected
        in {
            tuple(sorted((face[0], face[1]))),
            tuple(sorted((face[1], face[2]))),
            tuple(sorted((face[2], face[0]))),
        }
    ]
    if (
        len(source_edge_owners) != 2
        or patches[source_edge_owners[0]] != patches[source_edge_owners[1]]
        or groups[source_edge_owners[0]] != groups[source_edge_owners[1]]
    ):
        return rejected(
            "reject_strict_planar_flip_preflight", "flip_pair_or_patch_precondition_failed"
        )
    transaction = OperatorTransaction(source_vertices, source_faces)
    report = transaction.flip_edge(protected)
    if not report.accepted:
        return rejected("reject_strict_planar_flip_operator", report.reason)
    candidate_vertices = transaction.state.vertices
    candidate_faces = transaction.state.faces
    source_boundary, source_components, source_euler = _topology(source_faces, len(source_vertices))
    candidate_boundary, candidate_components, candidate_euler = _topology(
        candidate_faces, len(candidate_vertices)
    )
    boundary_ok = source_boundary == candidate_boundary
    topology_ok = source_components == candidate_components and source_euler == candidate_euler
    features_ok = feature_edges.issubset(set(_edges(candidate_faces)))
    vertices_ok = source_vertices.tobytes() == candidate_vertices.tobytes()
    changed = tuple(
        index
        for index in range(len(source_faces))
        if source_faces[index].tobytes() != candidate_faces[index].tobytes()
    )
    pair_vertices = set(source_faces[list(source_edge_owners)].reshape(-1).tolist())
    pair_candidate_vertices = set(candidate_faces[list(source_edge_owners)].reshape(-1).tolist())
    region_ok = (
        changed == tuple(source_edge_owners)
        and pair_vertices == pair_candidate_vertices
        and all(
            source_faces[index].tobytes() == candidate_faces[index].tobytes()
            for index in range(len(source_faces))
            if index not in source_edge_owners
        )
    )
    provenance_ok = vertices_ok and boundary_ok and topology_ok and features_ok and region_ok
    if not provenance_ok:
        return rejected("reject_strict_planar_flip_certificate", "source_region_certificate_failed")
    provenance = tuple(
        tuple(source_edge_owners) if index in source_edge_owners else (index,)
        for index in range(len(source_faces))
    )
    product = StrictPlanarFlipProduct(
        vertices=np.ascontiguousarray(candidate_vertices).copy(),
        faces=np.ascontiguousarray(candidate_faces).copy(),
        patch_ids=patches,
        physical_groups=groups,
        source_sha256=source.source_sha256,
        source_vertices_hash=_hash(source_vertices),
        source_faces_hash=_hash(source_faces),
        source_physical_groups_hash=source.physical_groups_sha256,
        face_region_provenance=provenance,
    )
    product.vertices.setflags(write=False)
    product.faces.setflags(write=False)
    return StrictPlanarFlipProductResult(
        True,
        "pass_strict_planar_flip_candidate",
        None,
        True,
        True,
        True,
        True,
        True,
        False,
        product,
    )
