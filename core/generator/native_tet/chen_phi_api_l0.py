"""Read-only Chen--Zheng-2006 Table-5 ``Phi`` neighbour lookup oracle.

For a decomposed pipel ``t``, ``Phi(t, vtx, fac)`` crosses the original face
opposite ``vtx``.  It returns the unique child in the already-decomposed
neighbour pipel that shares the requested new face ``fac``; unavailable or
ambiguous neighbours return no child.  This is a topology-only L0 contract and
does not apply any decomposition to a mesh.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.generator.native_tet.chen_pipe_cluster_l0 import IndexTet

FaceKey = tuple[int, int, int]


@dataclass(frozen=True)
class ChenPhiLookupResult:
    """Result of the fail-closed Table-5 neighbour lookup."""

    resolved: bool
    reason: str
    neighbor_tet: int | None
    child_tet: IndexTet | None


def _face_key(vertices: Sequence[int]) -> FaceKey:
    ordered = sorted(int(vertex) for vertex in vertices)
    if len(ordered) != 3 or len(set(ordered)) != 3:
        raise ValueError("a face must contain three distinct vertices")
    return ordered[0], ordered[1], ordered[2]


def _tet_faces(tet: IndexTet) -> tuple[FaceKey, FaceKey, FaceKey, FaceKey]:
    faces = [
        _face_key(tuple(tet[index] for index in range(4) if index != omitted))
        for omitted in range(4)
    ]
    return faces[0], faces[1], faces[2], faces[3]


def _as_index_tet(tet: Sequence[int]) -> IndexTet | None:
    values = tuple(int(vertex) for vertex in tet)
    if len(values) != 4 or len(set(values)) != 4:
        return None
    return values[0], values[1], values[2], values[3]


def _face_owners(tets: Sequence[IndexTet]) -> dict[FaceKey, tuple[int, ...]]:
    owners: dict[FaceKey, list[int]] = {}
    for index, tet in enumerate(tets):
        for face in _tet_faces(tet):
            owners.setdefault(face, []).append(index)
    return {face: tuple(indices) for face, indices in owners.items()}


def chen_phi_neighbor_lookup(
    parent_tets: Sequence[Sequence[int]],
    decomposed_children: Mapping[int, Sequence[Sequence[int]]],
    tet_index: int,
    opposite_vertex: int,
    requested_face: Sequence[int],
) -> ChenPhiLookupResult:
    """Implement the Table-5 ``Phi(t, vtx, fac)`` read-only contract."""
    parents = tuple(_as_index_tet(tet) for tet in parent_tets)
    if not parents or any(tet is None for tet in parents):
        return ChenPhiLookupResult(False, "invalid_parent_tetrahedron", None, None)
    typed_parents: tuple[IndexTet, ...] = tuple(tet for tet in parents if tet is not None)
    if tet_index < 0 or tet_index >= len(typed_parents):
        return ChenPhiLookupResult(False, "tet_index_out_of_range", None, None)
    parent = typed_parents[tet_index]
    if int(opposite_vertex) not in parent:
        return ChenPhiLookupResult(False, "opposite_vertex_not_in_parent", None, None)
    face = _face_key(requested_face)
    original_shared_face = _face_key(
        tuple(vertex for vertex in parent if vertex != int(opposite_vertex))
    )
    # A Table-5 requested child face must subdivide the original shared face;
    # without exact geometry, two retained original face vertices are the
    # smallest topology-only L0 admissibility test.
    if len(set(face).intersection(original_shared_face)) < 2:
        return ChenPhiLookupResult(False, "requested_face_not_on_original_shared_face", None, None)
    owners = _face_owners(typed_parents).get(original_shared_face, ())
    if len(owners) == 1:
        return ChenPhiLookupResult(False, "original_neighbor_is_null", None, None)
    if len(owners) != 2:
        return ChenPhiLookupResult(False, "original_neighbor_is_nonmanifold", None, None)
    neighbor = owners[0] if owners[1] == tet_index else owners[1]
    raw_children = decomposed_children.get(neighbor)
    if raw_children is None:
        return ChenPhiLookupResult(False, "neighbor_pipel_not_decomposed", neighbor, None)
    children = tuple(_as_index_tet(child) for child in raw_children)
    if not children or any(child is None for child in children):
        return ChenPhiLookupResult(False, "invalid_neighbor_dectets", neighbor, None)
    typed_children = tuple(child for child in children if child is not None)
    matches = tuple(child for child in typed_children if face in _tet_faces(child))
    if len(matches) != 1:
        return ChenPhiLookupResult(
            False,
            "requested_face_has_no_unique_neighbor_child",
            neighbor,
            None,
        )
    return ChenPhiLookupResult(True, "accepted", neighbor, matches[0])
