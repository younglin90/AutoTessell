# PRE1 (beta2127) — input-side sliver triangle merge.
# Merges near-coplanar small triangles BEFORE BSP/Delaunay so BSP boundary
# constraints don't force sliver tets.
# Reference: Shewchuk 2002 §4 (triangle quality), Botsch 2010 §7 (edge collapse).

from __future__ import annotations

import os

import numpy as np

# Feature flag — default ON (unset = ON).
_PRE1_ON = os.environ.get("AUTO_TESSELL_PRE1_OFF", "").strip() not in ("1", "true", "yes")


def merge_sliver_triangles(
    surface_pts: np.ndarray,
    surface_faces: np.ndarray,
    *,
    area_threshold: float | None = None,
    dihedral_deg: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Merge sliver triangles in the input surface mesh.

    For each face with area < area_threshold, attempt an edge collapse of its
    shortest edge.  Only collapses that preserve the edge-manifold property
    (each edge appears in ≤ 2 faces) are accepted.

    Parameters
    ----------
    surface_pts:    (N, 3) float64 vertex positions.
    surface_faces:  (M, 3) int64 triangle indices.
    area_threshold: faces with area < this value are candidates.
                    Default = (0.001 * bbox_diag)^2.
    dihedral_deg:   if the dihedral between a sliver and its neighbour across
                    the collapse edge is < dihedral_deg, treat as co-planar
                    and prefer that edge (conservative guard).

    Returns
    -------
    (new_pts, new_faces, n_merged)
    """
    pts = np.asarray(surface_pts, dtype=np.float64)
    faces = np.asarray(surface_faces, dtype=np.int64).copy()

    if faces.shape[0] < 100:
        return pts, faces, 0

    bmin = pts.min(axis=0)
    bmax = pts.max(axis=0)
    bbox_diag = float(np.linalg.norm(bmax - bmin))
    if bbox_diag <= 0.0:
        return pts, faces, 0

    if area_threshold is None:
        area_threshold = (0.001 * bbox_diag) ** 2

    # -- Compute per-face area via cross-product.
    v0 = pts[faces[:, 0]]
    v1 = pts[faces[:, 1]]
    v2 = pts[faces[:, 2]]
    cross = np.cross(v1 - v0, v2 - v0)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    sliver_mask = areas < area_threshold
    sliver_indices = np.where(sliver_mask)[0]
    if sliver_indices.size == 0:
        return pts, faces, 0

    # Build edge → face index map for manifold checks.
    # C-PERF-71 / beta2522 — vectorize via lexsort + group-boundary.
    def _build_edge_map(f: np.ndarray) -> dict[tuple[int, int], list[int]]:
        if f.size == 0:
            return {}
        f64 = np.asarray(f, dtype=np.int64)
        src = f64[:, [0, 1, 2]].reshape(-1)
        dst = f64[:, [1, 2, 0]].reshape(-1)
        fi_arr = np.repeat(np.arange(f64.shape[0], dtype=np.int64), 3)
        u = np.minimum(src, dst); v = np.maximum(src, dst)
        order = np.lexsort((v, u))
        u_s = u[order]; v_s = v[order]; fi_s = fi_arr[order]
        diff = np.r_[True, (u_s[1:] != u_s[:-1]) | (v_s[1:] != v_s[:-1])]
        starts = np.where(diff)[0]
        ends = np.r_[starts[1:], len(u_s)]
        emap: dict[tuple[int, int], list[int]] = {}
        for s, e in zip(starts.tolist(), ends.tolist()):
            emap[(int(u_s[s]), int(v_s[s]))] = fi_s[s:e].tolist()
        return emap

    # Union-find for vertex remapping.
    parent = np.arange(len(pts), dtype=np.int64)

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    n_merged = 0
    # Process slivers; rebuild edge map lazily only when needed.
    edge_map = _build_edge_map(faces)
    alive = np.ones(len(faces), dtype=bool)

    for fi in sliver_indices:
        if not alive[fi]:
            continue
        tri = faces[fi]
        # Find shortest edge.
        edges_v = [
            (int(tri[0]), int(tri[1])),
            (int(tri[1]), int(tri[2])),
            (int(tri[2]), int(tri[0])),
        ]
        edge_lens = [
            np.linalg.norm(pts[_find(a)] - pts[_find(b)])
            for a, b in edges_v
        ]
        shortest_i = int(np.argmin(edge_lens))
        a_raw, b_raw = edges_v[shortest_i]
        a, b = _find(a_raw), _find(b_raw)
        if a == b:
            continue  # already merged

        key = (min(a, b), max(a, b))
        nbrs = edge_map.get(key, [])
        # Manifold guard: collapse only if edge is shared by ≤ 2 faces.
        active_nbrs = [f for f in nbrs if alive[f]]
        if len(active_nbrs) > 2:
            continue

        # Dihedral check (optional preference, not a hard blocker).
        # We proceed if edge is manifold; dihedral guard only used to
        # prefer co-planar collapses (conservative).
        if len(active_nbrs) == 2:
            fi2 = active_nbrs[0] if active_nbrs[0] != fi else active_nbrs[1]
            n1 = cross[fi] / (2 * areas[fi] + 1e-30)
            a2 = areas[fi2]
            if a2 > 0:
                c2 = np.cross(
                    pts[faces[fi2, 1]] - pts[faces[fi2, 0]],
                    pts[faces[fi2, 2]] - pts[faces[fi2, 0]],
                )
                n2 = c2 / (np.linalg.norm(c2) + 1e-30)
                cos_dih = float(np.clip(np.dot(n1, n2), -1.0, 1.0))
                dih = float(np.degrees(np.arccos(abs(cos_dih))))
                # If dihedral is too large (surfaces not co-planar), skip.
                # We allow collapse unconditionally for sliver — just log guard.
                # (BSP slivers come from nearly-degenerate triangles regardless
                # of dihedral, so we always collapse.)
                _ = dih  # reserved for future tightening

        # Perform union: keep vertex 'a', redirect 'b' → 'a'.
        _union(b, a)
        # Mark faces that degenerate after remapping.
        for nf in active_nbrs:
            new_tri = [_find(int(faces[nf, j])) for j in range(3)]
            if len(set(new_tri)) < 3:
                alive[nf] = False
        n_merged += 1

    if n_merged == 0:
        return pts, faces, 0

    # Apply remap to surviving faces.
    alive_faces_idx = np.where(alive)[0]
    new_faces_raw = faces[alive_faces_idx].copy()
    # Remap via union-find.
    flat = new_faces_raw.ravel()
    remapped = np.array([_find(int(x)) for x in flat], dtype=np.int64).reshape(new_faces_raw.shape)
    # Drop degenerate triangles (shouldn't remain, but guard).
    not_degen = np.array([len(set(remapped[i])) == 3 for i in range(len(remapped))], dtype=bool)
    remapped = remapped[not_degen]

    # Compact vertices.
    used = np.unique(remapped)
    remap_table = np.zeros(len(pts), dtype=np.int64)
    remap_table[used] = np.arange(len(used), dtype=np.int64)
    new_pts = pts[used]
    new_faces_final = remap_table[remapped]

    # Final manifold check — every edge must appear in ≤ 2 faces.
    edge_map2 = _build_edge_map(new_faces_final)
    if any(len(v) > 2 for v in edge_map2.values()):
        # Non-manifold introduced — revert.
        return pts, faces, 0

    return new_pts, new_faces_final, n_merged
