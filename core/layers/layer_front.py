"""SMESH-style layer-edge advancing-front topology helpers.

This module is intentionally pure topology: it builds the wall-face front,
edge ownership and conservative validity sets before geometry extrusion.
native_bl.py can then use the same front for SetFaces / IgnoreFaces,
collision-aware growth and future per-edge advancement.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerEdge:
    """One edge on the layer front."""

    vertices: tuple[int, int]
    faces: tuple[int, ...]
    is_boundary: bool
    is_nonmanifold: bool


@dataclass(frozen=True)
class LayerFront:
    """Topology summary for a selected set of wall faces."""

    active_faces: tuple[int, ...]
    ignored_faces: tuple[int, ...]
    vertices: tuple[int, ...]
    edges: tuple[LayerEdge, ...]
    n_boundary_edges: int
    n_nonmanifold_edges: int


def build_layer_front(
    faces: list[list[int]],
    candidate_faces: list[int],
    *,
    strict_manifold: bool = False,
) -> LayerFront:
    """Build an advancing-front topology view for selected wall faces.

    Args:
        faces: mesh-global face connectivity.
        candidate_faces: absolute face ids selected by wall patches / SetFaces.
        strict_manifold: if true, faces touching non-manifold front edges are
            moved to ignored_faces. Default is diagnostic-only.
    """
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    face_edges: dict[int, list[tuple[int, int]]] = {}
    active_seed: list[int] = []
    for fi in candidate_faces:
        if fi < 0 or fi >= len(faces):
            continue
        f = [int(v) for v in faces[fi]]
        if len(f) < 3:
            continue
        active_seed.append(int(fi))
        local_edges: list[tuple[int, int]] = []
        for i, va in enumerate(f):
            vb = f[(i + 1) % len(f)]
            key = (va, vb) if va < vb else (vb, va)
            local_edges.append(key)
            edge_to_faces.setdefault(key, []).append(int(fi))
        face_edges[int(fi)] = local_edges

    nonmanifold_edges = {
        edge for edge, owners in edge_to_faces.items() if len(owners) > 2
    }
    ignored: set[int] = set()
    if strict_manifold and nonmanifold_edges:
        for fi, edges in face_edges.items():
            if any(edge in nonmanifold_edges for edge in edges):
                ignored.add(fi)

    active = tuple(fi for fi in active_seed if fi not in ignored)
    active_set = set(active)
    verts = sorted({int(v) for fi in active for v in faces[fi]})

    edges: list[LayerEdge] = []
    n_boundary = 0
    n_nonmanifold = 0
    for edge, owners in sorted(edge_to_faces.items()):
        owners_active = tuple(fi for fi in owners if fi in active_set)
        if not owners_active:
            continue
        is_boundary = len(owners_active) == 1
        is_nonmanifold = len(owners_active) > 2
        n_boundary += int(is_boundary)
        n_nonmanifold += int(is_nonmanifold)
        edges.append(
            LayerEdge(
                vertices=edge,
                faces=owners_active,
                is_boundary=is_boundary,
                is_nonmanifold=is_nonmanifold,
            )
        )

    return LayerFront(
        active_faces=active,
        ignored_faces=tuple(sorted(ignored)),
        vertices=tuple(verts),
        edges=tuple(edges),
        n_boundary_edges=n_boundary,
        n_nonmanifold_edges=n_nonmanifold,
    )
