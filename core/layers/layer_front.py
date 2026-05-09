"""SMESH-style layer-edge advancing-front topology helpers.

This module is intentionally pure topology: it builds the wall-face front,
edge ownership and conservative validity sets before geometry extrusion.
native_bl.py can then use the same front for SetFaces / IgnoreFaces,
collision-aware growth and future per-edge advancement.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LayerEdge:
    """One edge on the layer front."""

    vertices: tuple[int, int]
    faces: tuple[int, ...]
    is_boundary: bool
    is_nonmanifold: bool


@dataclass(frozen=True)
class LayerVertex:
    """SMESH-style advancement state for one source wall vertex.

    This is the Python analogue of the per-node layer-edge graph used by
    viscous-layer front methods: each wall vertex knows its adjacent wall
    faces, incident front edges, neighbouring wall vertices and whether it is
    geometrically blocked by a feature, boundary, or non-manifold front.
    """

    vertex: int
    faces: tuple[int, ...]
    edge_indices: tuple[int, ...]
    neighbours: tuple[int, ...]
    is_boundary: bool
    is_nonmanifold: bool
    is_feature: bool
    is_blocked: bool
    normal: tuple[float, float, float] | None


@dataclass(frozen=True)
class LayerFront:
    """Topology summary for a selected set of wall faces."""

    active_faces: tuple[int, ...]
    ignored_faces: tuple[int, ...]
    vertices: tuple[int, ...]
    edges: tuple[LayerEdge, ...]
    n_boundary_edges: int
    n_nonmanifold_edges: int
    layer_vertices: tuple[LayerVertex, ...] = ()
    n_feature_vertices: int = 0
    n_blocked_vertices: int = 0


@dataclass(frozen=True)
class LayerMoveCheck:
    """Validity result for a proposed layer-edge point move."""

    accepted: bool
    min_abs_volume_before: float
    min_abs_volume_after: float
    n_checked: int
    reason: str = ""


def _tet_volume6(
    moving: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
) -> float:
    return float(np.dot(np.cross(a - moving, b - moving), c - moving))


def check_layer_point_move(
    points: np.ndarray,
    moving_vertex: int,
    candidate: np.ndarray,
    simplices: list[tuple[int, int, int]],
    *,
    min_abs_volume: float = 1e-14,
    require_non_decreasing: bool = True,
) -> LayerMoveCheck:
    """Check whether a layer-edge move preserves local simplex validity.

    This mirrors the guard used by advancing-layer methods before accepting a
    smoothed layer-edge position: all incident simplex orientations must remain
    forward and sufficiently non-degenerate.  ``simplices`` are the three
    stationary vertex ids around ``moving_vertex``.
    """
    if not simplices:
        return LayerMoveCheck(
            accepted=False,
            min_abs_volume_before=0.0,
            min_abs_volume_after=0.0,
            n_checked=0,
            reason="no_simplices",
        )

    pts = np.asarray(points, dtype=np.float64)
    cur = pts[int(moving_vertex)]
    cand = np.asarray(candidate, dtype=np.float64)
    before_abs: list[float] = []
    after_abs: list[float] = []
    for a_i, b_i, c_i in simplices:
        a = pts[int(a_i)]
        b = pts[int(b_i)]
        c = pts[int(c_i)]
        vol_before = _tet_volume6(cur, a, b, c)
        vol_after = _tet_volume6(cand, a, b, c)
        abs_before = abs(vol_before)
        abs_after = abs(vol_after)
        before_abs.append(abs_before)
        after_abs.append(abs_after)
        if abs_before <= min_abs_volume:
            return LayerMoveCheck(
                accepted=False,
                min_abs_volume_before=float(min(before_abs)),
                min_abs_volume_after=float(min(after_abs)),
                n_checked=len(before_abs),
                reason="degenerate_before",
            )
        if abs_after <= min_abs_volume:
            return LayerMoveCheck(
                accepted=False,
                min_abs_volume_before=float(min(before_abs)),
                min_abs_volume_after=float(min(after_abs)),
                n_checked=len(before_abs),
                reason="degenerate_after",
            )
        if vol_before * vol_after <= 0.0:
            return LayerMoveCheck(
                accepted=False,
                min_abs_volume_before=float(min(before_abs)),
                min_abs_volume_after=float(min(after_abs)),
                n_checked=len(before_abs),
                reason="orientation_flip",
            )

    min_before = float(min(before_abs))
    min_after = float(min(after_abs))
    if require_non_decreasing and min_after < min_before:
        return LayerMoveCheck(
            accepted=False,
            min_abs_volume_before=min_before,
            min_abs_volume_after=min_after,
            n_checked=len(before_abs),
            reason="volume_decreased",
        )

    return LayerMoveCheck(
        accepted=True,
        min_abs_volume_before=min_before,
        min_abs_volume_after=min_after,
        n_checked=len(before_abs),
    )


def _unit_face_normal(
    faces: list[list[int]],
    points: np.ndarray,
    fi: int,
) -> np.ndarray | None:
    f = faces[fi]
    if len(f) < 3:
        return None
    p0 = np.asarray(points[f[0]], dtype=np.float64)
    p1 = np.asarray(points[f[1]], dtype=np.float64)
    p2 = np.asarray(points[f[2]], dtype=np.float64)
    n_raw = np.cross(p1 - p0, p2 - p0)
    mag = float(np.linalg.norm(n_raw))
    if mag < 1e-30:
        return None
    return n_raw / mag


def build_layer_front(
    faces: list[list[int]],
    candidate_faces: list[int],
    *,
    strict_manifold: bool = False,
    points: np.ndarray | None = None,
    feature_cos_thresh: float = 0.9,
) -> LayerFront:
    """Build an advancing-front topology view for selected wall faces.

    Args:
        faces: mesh-global face connectivity.
        candidate_faces: absolute face ids selected by wall patches / SetFaces.
        strict_manifold: if true, faces touching non-manifold front edges are
            moved to ignored_faces. Default is diagnostic-only.
        points: optional mesh points. When supplied, per-vertex normals and
            feature flags are computed from adjacent active face normals.
        feature_cos_thresh: a source vertex is a feature if any adjacent active
            face-normal pair has cosine below this threshold.
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
    edge_index_by_key: dict[tuple[int, int], int] = {}
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
        edge_index_by_key[edge] = len(edges)
        edges.append(
            LayerEdge(
                vertices=edge,
                faces=owners_active,
                is_boundary=is_boundary,
                is_nonmanifold=is_nonmanifold,
            )
        )

    face_normals: dict[int, np.ndarray] = {}
    if points is not None:
        for fi in active:
            n = _unit_face_normal(faces, points, fi)
            if n is not None:
                face_normals[fi] = n

    v_to_faces: dict[int, list[int]] = {v: [] for v in verts}
    v_to_edge_indices: dict[int, list[int]] = {v: [] for v in verts}
    v_to_neighbours: dict[int, set[int]] = {v: set() for v in verts}
    for fi in active:
        for v in faces[fi]:
            if int(v) in v_to_faces:
                v_to_faces[int(v)].append(int(fi))
    for edge, ei in edge_index_by_key.items():
        va, vb = edge
        if va in v_to_edge_indices:
            v_to_edge_indices[va].append(ei)
            v_to_neighbours[va].add(vb)
        if vb in v_to_edge_indices:
            v_to_edge_indices[vb].append(ei)
            v_to_neighbours[vb].add(va)

    layer_vertices: list[LayerVertex] = []
    for v in verts:
        incident_edge_ids = tuple(sorted(v_to_edge_indices.get(v, [])))
        incident_edges = [edges[ei] for ei in incident_edge_ids]
        is_boundary = any(e.is_boundary for e in incident_edges)
        is_nonmanifold = any(e.is_nonmanifold for e in incident_edges)

        adj_face_ids = tuple(sorted(set(v_to_faces.get(v, []))))
        normals = [face_normals[fi] for fi in adj_face_ids if fi in face_normals]
        normal_tuple: tuple[float, float, float] | None = None
        is_feature = False
        if normals:
            n_avg = np.sum(np.stack(normals, axis=0), axis=0)
            mag = float(np.linalg.norm(n_avg))
            if mag > 1e-30:
                n_avg = n_avg / mag
                normal_tuple = (
                    float(n_avg[0]),
                    float(n_avg[1]),
                    float(n_avg[2]),
                )
            if len(normals) >= 2:
                normal_stack = np.stack(normals, axis=0)
                coss = normal_stack @ normal_stack.T
                np.fill_diagonal(coss, 1.0)
                is_feature = float(coss.min()) < float(feature_cos_thresh)

        layer_vertices.append(
            LayerVertex(
                vertex=int(v),
                faces=adj_face_ids,
                edge_indices=incident_edge_ids,
                neighbours=tuple(sorted(v_to_neighbours.get(v, set()))),
                is_boundary=is_boundary,
                is_nonmanifold=is_nonmanifold,
                is_feature=is_feature,
                is_blocked=bool(is_boundary or is_nonmanifold or is_feature),
                normal=normal_tuple,
            )
        )

    n_feature_vertices = sum(1 for v in layer_vertices if v.is_feature)
    n_blocked_vertices = sum(1 for v in layer_vertices if v.is_blocked)

    return LayerFront(
        active_faces=active,
        ignored_faces=tuple(sorted(ignored)),
        vertices=tuple(verts),
        edges=tuple(edges),
        n_boundary_edges=n_boundary,
        n_nonmanifold_edges=n_nonmanifold,
        layer_vertices=tuple(layer_vertices),
        n_feature_vertices=int(n_feature_vertices),
        n_blocked_vertices=int(n_blocked_vertices),
    )
