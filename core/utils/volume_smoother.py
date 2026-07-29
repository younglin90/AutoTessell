"""Volumetric Taubin smoother for polyMesh interior vertices.

Iter-0004 autoresearch — addresses tet/hex/poly + BL Standard-gate non-orthogonality
and skewness by moving INTERIOR vertices toward neighbor centroids, while
keeping boundary vertices fixed (preserves Hausdorff fidelity).

Taubin (1995) two-pass scheme:
  x_i ← x_i + λ ( mean(neighbours) − x_i )      # shrink
  x_i ← x_i − μ ( mean(neighbours) − x_i )      # inflate (volume preserve)

Default λ = 0.5, μ = 0.53 (slight bias to avoid pure-Laplacian shrinkage).

External-library reference (we copy the idea, not the code): pyACVD /
pymeshlab `taubin_smoothing`, OpenFOAM `volumeSmoothMesh`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
)

from core.utils.drop_neg_vol_cells import (
    _read_points,
    _signed_cell_volumes,
    _write_points,
)


def _build_vertex_adjacency(
    faces: list[list[int]], n_pts: int,
) -> list[set[int]]:
    adj: list[set[int]] = [set() for _ in range(n_pts)]
    for f in faces:
        k = len(f)
        for i in range(k):
            a = int(f[i])
            b = int(f[(i + 1) % k])
            adj[a].add(b)
            adj[b].add(a)
    return adj


def _boundary_vertex_mask(
    faces: list[list[int]],
    n_pts: int,
    patches: list[dict[str, Any]],
    n_internal: int,
) -> np.ndarray:
    """Vertices on any boundary face are pinned."""
    mask = np.zeros(n_pts, dtype=bool)
    # Boundary faces = those at index >= n_internal.
    for fi in range(n_internal, len(faces)):
        for v in faces[fi]:
            mask[int(v)] = True
    # Defensive: patches' startFace also defines boundary cells.
    for patch in patches:
        start = int(patch.get("startFace", 0))
        nf = int(patch.get("nFaces", 0))
        for fi in range(start, start + nf):
            if 0 <= fi < len(faces):
                for v in faces[fi]:
                    mask[int(v)] = True
    return mask


def taubin_smooth_polymesh(
    case_dir: Path,
    *,
    n_iterations: int = 5,
    lambda_pos: float = 0.5,
    mu_neg: float = 0.53,
    skip_if_n_pts_below: int = 50,
) -> dict[str, Any]:
    """Apply Taubin smoothing to interior vertices of `case_dir/constant/polyMesh`.

    Boundary vertices (any vertex of any boundary face) are fixed.  The
    polyMesh is rewritten in place; only `points` changes.  Topology
    (`faces`, `owner`, `neighbour`, `boundary`) is preserved exactly.
    """
    poly = case_dir / "constant" / "polyMesh"
    pts = _read_points(poly / "points").astype(np.float64)
    faces = [list(f) for f in parse_foam_faces(poly / "faces")]
    owner_arr = np.asarray(parse_foam_labels(poly / "owner"), dtype=np.int64)
    neighbour_raw = parse_foam_labels(poly / "neighbour")
    patches = parse_foam_boundary(poly / "boundary")

    # iter-0008 (2026-05-15): strip cfMesh-style -1 sentinels.  Same fix
    # we landed in NativeMeshChecker — keep the smoother consistent.
    neighbour = np.asarray(neighbour_raw, dtype=np.int64)
    if patches:
        _min_start = min(int(p.get("startFace", len(faces))) for p in patches)
        if 0 < _min_start < neighbour.shape[0]:
            neighbour = neighbour[:_min_start]
    if neighbour.size and (neighbour < 0).any():
        neighbour = neighbour[neighbour >= 0]
    n_cells_smoother = max(
        int(owner_arr.max()) if owner_arr.size else -1,
        int(neighbour.max()) if neighbour.size else -1,
    ) + 1

    n_pts = pts.shape[0]
    if n_pts < skip_if_n_pts_below:
        return {"skipped": True, "reason": f"n_pts={n_pts} < {skip_if_n_pts_below}"}

    n_internal = int(neighbour.shape[0])
    adj = _build_vertex_adjacency(faces, n_pts)
    bdry = _boundary_vertex_mask(faces, n_pts, patches, n_internal)

    # iter-0008 (2026-05-15): per-cell volume guard — rollback any vertex
    # whose move flipped or near-degenerated an incident cell.  Mesquite
    # / Knupp-style local quality check, lightweight version.
    initial_vols = _signed_cell_volumes(
        pts, faces, owner_arr, neighbour, n_cells_smoother,
    )
    # Map vertex → set of incident cells, via face → owner/neighbour.
    vert_cells: list[set[int]] = [set() for _ in range(n_pts)]
    for fi, f in enumerate(faces):
        own_c = int(owner_arr[fi])
        for v in f:
            vert_cells[int(v)].add(own_c)
        if fi < n_internal:
            nb_c = int(neighbour[fi])
            for v in f:
                vert_cells[int(v)].add(nb_c)

    interior_idx = np.where(~bdry)[0]
    if interior_idx.size == 0:
        return {"skipped": True, "reason": "no_interior_vertices",
                "n_pts": n_pts, "n_boundary": int(bdry.sum())}

    # Pre-compute neighbor lists for interior vertices for vectorized
    # mean.  Use a sparse representation: flat arrays of (vi, vj).
    flat_vi: list[int] = []
    flat_vj: list[int] = []
    for vi in interior_idx:
        nbrs = adj[int(vi)]
        if not nbrs:
            continue
        for vj in nbrs:
            flat_vi.append(int(vi))
            flat_vj.append(int(vj))
    if not flat_vi:
        return {"skipped": True, "reason": "no_interior_edges",
                "n_pts": n_pts}
    flat_vi_a = np.asarray(flat_vi, dtype=np.int64)
    flat_vj_a = np.asarray(flat_vj, dtype=np.int64)

    # Count neighbors per interior vertex (for averaging).
    nbr_counts = np.bincount(flat_vi_a, minlength=n_pts).astype(np.float64)
    safe_counts = np.where(nbr_counts > 0, nbr_counts, 1.0)

    # iter-0005: per-vertex displacement cap.  BL prism cells have
    # first-layer thickness ≈ 1e-4 of bbox; a 0.5*Laplacian step can
    # flip them.  Cap each iteration's displacement at
    # `disp_cap_ratio` × (shortest incident edge of that vertex).
    DISP_CAP_RATIO = 0.15  # safe margin against inversion
    # Pre-compute shortest incident edge per vertex (once).
    edge_lens = np.linalg.norm(
        pts[flat_vi_a] - pts[flat_vj_a], axis=1,
    )
    min_edge = np.full(n_pts, np.inf, dtype=np.float64)
    for i in range(flat_vi_a.shape[0]):
        v = int(flat_vi_a[i])
        e = float(edge_lens[i])
        if e > 0 and e < min_edge[v]:
            min_edge[v] = e
    cap = np.where(np.isfinite(min_edge), DISP_CAP_RATIO * min_edge, np.inf)

    def _cap_displacement(delta_arr: np.ndarray) -> np.ndarray:
        mag = np.linalg.norm(delta_arr, axis=1)
        safe_mag = np.where(mag > 1e-30, mag, 1.0)
        scale = np.minimum(1.0, cap / safe_mag)
        return delta_arr * scale[:, None]

    def _rollback_bad_cells(
        candidate_pts: np.ndarray, prev_pts: np.ndarray,
    ) -> tuple[np.ndarray, int]:
        """If a Taubin step would flip a cell, rollback the verts of
        that cell to prev_pts.  Returns (safe_pts, n_rolled_back)."""
        new_vols = _signed_cell_volumes(
            candidate_pts, faces, owner_arr, neighbour, n_cells_smoother,
        )
        # Flag cells where sign flipped OR |vol| collapsed below 10 % of original
        flipped = (initial_vols * new_vols < 0)
        collapsed = (
            (np.abs(new_vols) < 0.1 * np.abs(initial_vols))
            & (np.abs(initial_vols) > 0)
        )
        bad_cells = np.where(flipped | collapsed)[0]
        if bad_cells.size == 0:
            return candidate_pts, 0
        # Rollback every vertex incident to any bad cell.
        verts_to_rollback: set[int] = set()
        for ci in bad_cells:
            ci_int = int(ci)
            # vert_cells[v] contains ci for each v on a face of c. Need reverse: iterate.
            # We use a precomputed `cell_verts`.
            pass
        # Simpler & adequate: rebuild reverse map lazily.
        cell_verts_local: dict[int, set[int]] = {}
        for fi, f in enumerate(faces):
            own_c = int(owner_arr[fi])
            if own_c in set(int(c) for c in bad_cells):
                cell_verts_local.setdefault(own_c, set()).update(int(v) for v in f)
            if fi < n_internal:
                nb_c = int(neighbour[fi])
                if nb_c in set(int(c) for c in bad_cells):
                    cell_verts_local.setdefault(nb_c, set()).update(int(v) for v in f)
        for s in cell_verts_local.values():
            verts_to_rollback.update(s)
        if not verts_to_rollback:
            return candidate_pts, 0
        idx = np.fromiter(verts_to_rollback, dtype=np.int64)
        # Keep boundary verts at their (unchanged) positions; non-bdry get reverted.
        candidate_pts = candidate_pts.copy()
        candidate_pts[idx] = prev_pts[idx]
        return candidate_pts, int(bad_cells.size)

    max_disp = 0.0
    n_rolled = 0
    for _ in range(n_iterations):
        prev_pts = pts.copy()
        # λ step (shrink) with cap
        nbr_sum = np.zeros_like(pts)
        np.add.at(nbr_sum, flat_vi_a, pts[flat_vj_a])
        mean_nbr = nbr_sum / safe_counts[:, None]
        delta = mean_nbr - pts
        delta[bdry] = 0.0
        delta = _cap_displacement(lambda_pos * delta)
        new_pts = pts + delta
        # μ step (inflate) with cap
        nbr_sum2 = np.zeros_like(new_pts)
        np.add.at(nbr_sum2, flat_vi_a, new_pts[flat_vj_a])
        mean_nbr2 = nbr_sum2 / safe_counts[:, None]
        delta2 = mean_nbr2 - new_pts
        delta2[bdry] = 0.0
        delta2 = _cap_displacement(mu_neg * delta2)
        candidate = new_pts - delta2
        # Per-cell volume guard
        candidate, n_bad = _rollback_bad_cells(candidate, prev_pts)
        n_rolled += n_bad
        pts = candidate
        max_disp = max(max_disp, float(np.linalg.norm(delta[~bdry], axis=1).max()))

    _write_points(poly / "points", pts)
    return {
        "skipped": False,
        "n_pts": int(n_pts),
        "n_interior": int(interior_idx.size),
        "n_boundary": int(bdry.sum()),
        "n_iterations": int(n_iterations),
        "lambda": float(lambda_pos),
        "mu": float(mu_neg),
        "max_displacement": float(max_disp),
        "n_cells_rolled_back": int(n_rolled),
    }
