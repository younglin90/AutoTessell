"""OpenFOAM-free mesh quality checker using numpy only.

Reads the five polyMesh files (points, faces, owner, neighbour, boundary)
and computes checkMesh-equivalent quality metrics without requiring any
OpenFOAM installation.  This makes it usable on Windows and in CI
environments that do not ship OpenFOAM.

Metrics computed
----------------
- cells, faces, points counts
- max / avg non-orthogonality (degrees)
- max skewness
- max aspect ratio (per cell: max_edge / min_edge)
- min face area
- min / max cell volume
- min determinant (conservative estimate)
- negative volume count
- severely non-orthogonal face count (> 70 degrees)

neatmesh integration
--------------------
If the ``neatmesh`` package is installed, ``NativeMeshChecker`` exposes the
``run_neatmesh`` helper which accepts a meshio-compatible mesh file (e.g. a
VTK or Gmsh file) and returns supplementary quality statistics computed by
neatmesh's ``Analyzer3D``.  Import errors are silently ignored so the module
works without neatmesh.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.schemas import CheckMeshResult
from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)

log = get_logger(__name__)

try:
    import meshio as _meshio
    from neatmesh._analyzer import Analyzer3D as _NeatAnalyzer3D
    from neatmesh._reader import MeshReader3D as _NeatReader3D
    _NEATMESH_AVAILABLE = True
except ImportError:
    _meshio = None
    _NeatAnalyzer3D = None
    _NeatReader3D = None
    _NEATMESH_AVAILABLE = False


class NativeMeshChecker:
    """OpenFOAM-free mesh quality checker using numpy."""

    # Non-orthogonality above this (degrees) → "severely non-orthogonal"
    SEVERE_NON_ORTHO_THRESHOLD: float = 70.0

    def run(self, case_dir: Path) -> CheckMeshResult:
        """Read polyMesh files and compute quality metrics.

        Args:
            case_dir: OpenFOAM case directory (must contain
                ``constant/polyMesh/``).

        Returns:
            CheckMeshResult populated from native numpy calculations.

        Raises:
            FileNotFoundError: If the polyMesh directory or required files
                are missing.
        """
        poly_dir = case_dir / "constant" / "polyMesh"
        if not poly_dir.is_dir():
            raise FileNotFoundError(
                f"polyMesh 디렉터리 없음: {poly_dir}"
            )

        log.info("NativeMeshChecker.run", poly_dir=str(poly_dir))

        # ------------------------------------------------------------------
        # 1. Parse files
        # ------------------------------------------------------------------
        points_file = poly_dir / "points"
        faces_file = poly_dir / "faces"
        owner_file = poly_dir / "owner"
        neighbour_file = poly_dir / "neighbour"
        boundary_file = poly_dir / "boundary"

        for f in (points_file, faces_file, owner_file, neighbour_file, boundary_file):
            if not f.exists():
                raise FileNotFoundError(f"polyMesh 파일 없음: {f}")

        raw_points = parse_foam_points(points_file)
        raw_faces = parse_foam_faces(faces_file)
        owner_list = parse_foam_labels(owner_file)
        neighbour_list = parse_foam_labels(neighbour_file)
        parse_foam_boundary(boundary_file)

        if not raw_points or not raw_faces or not owner_list:
            log.warning("Empty polyMesh — returning degenerate CheckMeshResult")
            return self._empty_result()

        points = np.array(raw_points, dtype=np.float64)  # (N, 3)
        owner = np.array(owner_list, dtype=np.int64)       # (F,)
        neighbour = np.array(neighbour_list, dtype=np.int64)  # (I,)

        n_points = len(points)
        n_faces = len(raw_faces)
        n_internal = len(neighbour)
        max_cell_id = int(owner.max()) if len(owner) > 0 else -1
        if len(neighbour) > 0:
            max_cell_id = max(max_cell_id, int(neighbour.max()))
        n_cells = max_cell_id + 1

        log.debug(
            "native_checker_parsed",
            n_points=n_points,
            n_faces=n_faces,
            n_internal=n_internal,
            n_cells=n_cells,
        )

        # ------------------------------------------------------------------
        # 2. Pre-compute face centres and face normals (area-weighted)
        # ------------------------------------------------------------------
        face_centres = self._compute_face_centres(points, raw_faces)   # (F, 3)
        face_normals, face_areas = self._compute_face_normals_areas(points, raw_faces)
        # face_normals: (F, 3) unit normals; face_areas: (F,) scalar areas

        # ------------------------------------------------------------------
        # 3. Cell centres (average of constituent face centres)
        # ------------------------------------------------------------------
        cell_centres = self._compute_cell_centres(face_centres, owner, n_cells, neighbour)  # (C, 3)

        # ------------------------------------------------------------------
        # 4. Non-orthogonality (internal faces only)
        # ------------------------------------------------------------------
        max_non_ortho, avg_non_ortho, severe_count = self._compute_non_orthogonality(
            face_centres, face_normals, cell_centres, owner, neighbour, n_internal
        )

        # ------------------------------------------------------------------
        # 5. Skewness (internal faces only)
        # ------------------------------------------------------------------
        max_skewness = self._compute_skewness(
            face_centres, cell_centres, owner, neighbour, n_internal
        )

        # ------------------------------------------------------------------
        # 6. Cell volumes (signed divergence theorem)
        # ------------------------------------------------------------------
        cell_volumes, negative_volumes = self._compute_cell_volumes(
            points, raw_faces, face_normals, face_areas, owner, neighbour,
            n_cells, n_internal
        )

        # ------------------------------------------------------------------
        # 7. Aspect ratios (per cell: max edge / min edge via face vertices)
        # ------------------------------------------------------------------
        max_aspect_ratio = self._compute_max_aspect_ratio(
            points, raw_faces, owner, n_cells, n_internal
        )

        # ------------------------------------------------------------------
        # 8. Min face area
        # ------------------------------------------------------------------
        min_face_area = float(face_areas.min()) if len(face_areas) > 0 else 0.0

        # ------------------------------------------------------------------
        # 9. Min cell volume / volume stats
        # ------------------------------------------------------------------
        if len(cell_volumes) > 0:
            min_cell_volume = float(cell_volumes.min())
            float(cell_volumes.max())
        else:
            min_cell_volume = 0.0

        # ------------------------------------------------------------------
        # 10. Min determinant (conservative: scaled volume ratio per cell)
        # ------------------------------------------------------------------
        min_determinant = self._estimate_min_determinant(cell_volumes)

        # ------------------------------------------------------------------
        # 11. failed_checks / mesh_ok heuristic
        # ------------------------------------------------------------------
        # NativeMeshChecker는 OpenFOAM checkMesh의 "Failed N mesh checks"를
        # 모방한다. OpenFOAM은 negative volumes/zero volumes만 failed check으로
        # 카운트하고, non-ortho/skewness 등은 warning으로 처리한다.
        # Note: divergence theorem 볼륨 계산은 부동소수점 오차로 인해
        # 매우 작은 음수값(-1e-15 등)이 발생할 수 있다. 의미있는 negative volume
        # 검출을 위해 상대 임계값을 사용한다.
        # negative_volumes는 _compute_cell_volumes에서 이미 상대 tolerance로 카운트
        meaningful_neg_volumes = negative_volumes

        failed_checks = 0
        if meaningful_neg_volumes > 0:
            failed_checks += 1

        mesh_ok = failed_checks == 0

        result = CheckMeshResult(
            cells=n_cells,
            faces=n_faces,
            points=n_points,
            max_non_orthogonality=float(max_non_ortho),
            avg_non_orthogonality=float(avg_non_ortho),
            max_skewness=float(max_skewness),
            max_aspect_ratio=float(max_aspect_ratio),
            min_face_area=float(min_face_area),
            min_cell_volume=float(min_cell_volume),
            min_determinant=float(min_determinant),
            negative_volumes=meaningful_neg_volumes,
            severely_non_ortho_faces=int(severe_count),
            failed_checks=int(failed_checks),
            mesh_ok=mesh_ok,
        )

        log.info(
            "NativeMeshChecker done",
            cells=n_cells,
            max_non_ortho=max_non_ortho,
            max_skewness=max_skewness,
            negative_volumes=negative_volumes,
            mesh_ok=mesh_ok,
        )
        return result

    # ------------------------------------------------------------------
    # Face geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_face_centres(
        points: np.ndarray, faces: list[list[int]]
    ) -> np.ndarray:
        """Return (F, 3) array of face centres (average of vertices)."""
        centres = np.zeros((len(faces), 3), dtype=np.float64)
        for i, face in enumerate(faces):
            centres[i] = points[face].mean(axis=0)
        return centres

    @staticmethod
    def _compute_face_normals_areas(
        points: np.ndarray, faces: list[list[int]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return unit normals (F, 3) and areas (F,) using fan triangulation."""
        n = len(faces)
        normals = np.zeros((n, 3), dtype=np.float64)
        areas = np.zeros(n, dtype=np.float64)

        for i, face in enumerate(faces):
            if len(face) < 3:
                continue
            verts = points[face]
            # Fan triangulate from vertex 0
            v0 = verts[0]
            area_vec = np.zeros(3, dtype=np.float64)
            for k in range(1, len(face) - 1):
                e1 = verts[k] - v0
                e2 = verts[k + 1] - v0
                area_vec += np.cross(e1, e2)
            mag = np.linalg.norm(area_vec)
            areas[i] = mag * 0.5
            if mag > 0.0:
                normals[i] = area_vec / mag

        return normals, areas

    # ------------------------------------------------------------------
    # Cell geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_cell_centres(
        face_centres: np.ndarray,
        owner: np.ndarray,
        n_cells: int,
        neighbour: np.ndarray | None = None,
    ) -> np.ndarray:
        """Return (C, 3) cell centres as the mean of belonging face centres.

        Each face contributes to its owner cell; internal faces also contribute
        to the neighbour cell.
        """
        centres = np.zeros((n_cells, 3), dtype=np.float64)
        counts = np.zeros(n_cells, dtype=np.int64)
        np.add.at(centres, owner, face_centres)
        np.add.at(counts, owner, 1)
        if neighbour is not None and len(neighbour) > 0:
            n_internal = len(neighbour)
            np.add.at(centres, neighbour, face_centres[:n_internal])
            np.add.at(counts, neighbour, 1)
        nonzero = counts > 0
        centres[nonzero] /= counts[nonzero, np.newaxis]
        return centres

    # ------------------------------------------------------------------
    # Non-orthogonality
    # ------------------------------------------------------------------

    def _compute_non_orthogonality(
        self,
        face_centres: np.ndarray,
        face_normals: np.ndarray,
        cell_centres: np.ndarray,
        owner: np.ndarray,
        neighbour: np.ndarray,
        n_internal: int,
    ) -> tuple[float, float, int]:
        """Compute max/avg non-orthogonality (degrees) for internal faces.

        Non-orthogonality of face i is the angle between the face outward
        normal and the vector from owner cell centre to neighbour cell centre.

        Returns:
            (max_degrees, avg_degrees, severe_count)
        """
        if n_internal == 0:
            return 0.0, 0.0, 0

        own_idx = owner[:n_internal]
        nbr_idx = neighbour[:n_internal]

        # d: owner → neighbour
        d = cell_centres[nbr_idx] - cell_centres[own_idx]           # (I, 3)
        n_hat = face_normals[:n_internal]                            # (I, 3)

        d_mag = np.linalg.norm(d, axis=1)                           # (I,)
        n_mag = np.linalg.norm(n_hat, axis=1)                       # (I,)

        # Only compute for faces with valid vectors
        valid = (d_mag > 1e-30) & (n_mag > 1e-30)
        if not np.any(valid):
            return 0.0, 0.0, 0

        cos_theta = np.einsum("ij,ij->i", d[valid], n_hat[valid]) / (
            d_mag[valid] * n_mag[valid]
        )
        # Clamp to [-1, 1] to guard against floating-point drift
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        angles_deg = np.degrees(np.arccos(cos_theta))

        max_non_ortho = float(angles_deg.max())
        avg_non_ortho = float(angles_deg.mean())
        severe_count = int(np.sum(angles_deg > self.SEVERE_NON_ORTHO_THRESHOLD))

        return max_non_ortho, avg_non_ortho, severe_count

    # ------------------------------------------------------------------
    # Skewness
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_skewness(
        face_centres: np.ndarray,
        cell_centres: np.ndarray,
        owner: np.ndarray,
        neighbour: np.ndarray,
        n_internal: int,
    ) -> float:
        """Max skewness over internal faces.

        Skewness = distance from face centre to the line connecting the two
        cell centres, divided by that cell-centre distance.
        """
        if n_internal == 0:
            return 0.0

        own_idx = owner[:n_internal]
        nbr_idx = neighbour[:n_internal]

        p_own = cell_centres[own_idx]   # (I, 3)
        p_nbr = cell_centres[nbr_idx]   # (I, 3)
        fc = face_centres[:n_internal]  # (I, 3)

        d = p_nbr - p_own               # (I, 3)
        d_mag = np.linalg.norm(d, axis=1)  # (I,)

        valid = d_mag > 1e-30
        if not np.any(valid):
            return 0.0

        # Project face centre onto the line p_own + t * d
        diff = fc[valid] - p_own[valid]
        t = np.einsum("ij,ij->i", diff, d[valid]) / (d_mag[valid] ** 2)
        proj = p_own[valid] + t[:, np.newaxis] * d[valid]  # (I', 3)

        skew_dist = np.linalg.norm(fc[valid] - proj, axis=1)
        skewness = skew_dist / d_mag[valid]

        return float(skewness.max())

    # ------------------------------------------------------------------
    # Cell volumes (divergence theorem)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_cell_volumes(
        points: np.ndarray,
        faces: list[list[int]],
        face_normals: np.ndarray,
        face_areas: np.ndarray,
        owner: np.ndarray,
        neighbour: np.ndarray,
        n_cells: int,
        n_internal: int,
    ) -> tuple[np.ndarray, int]:
        """Estimate cell volumes using the divergence theorem.

        V = (1/3) * sum_f ( face_centre · face_normal * face_area * sign )

        where sign = +1 if the face normal points out of the cell,
        -1 if it points in.

        By the polyMesh convention:
        - For internal faces: normal points from owner to neighbour
          → +1 for owner, -1 for neighbour.
        - For boundary faces: normal points outward from owner → +1.

        Returns:
            (cell_volumes array, count of negative volumes)
        """
        n_faces = len(faces)

        # Face centres
        fc = np.zeros((n_faces, 3), dtype=np.float64)
        for i, face in enumerate(faces):
            fc[i] = points[face].mean(axis=0)

        # Contribution: face_centre · unit_normal * area
        # Using area-weighted normals so we can skip the area separately
        contribution = np.einsum("ij,ij->i", fc, face_normals) * face_areas  # (F,)

        volumes = np.zeros(n_cells, dtype=np.float64)

        # Internal faces: +1 for owner, -1 for neighbour
        if n_internal > 0:
            own_idx = owner[:n_internal]
            nbr_idx = neighbour[:n_internal]
            np.add.at(volumes, own_idx, contribution[:n_internal])
            np.subtract.at(volumes, nbr_idx, contribution[:n_internal])

        # Boundary faces: +1 for owner
        if n_faces > n_internal:
            bnd_owners = owner[n_internal:]
            np.add.at(volumes, bnd_owners, contribution[n_internal:])

        volumes /= 3.0

        # Divergence theorem은 distorted 셀에서 작은 음수를 반환할 수 있다.
        # 의미있는 negative volume은 mean volume 대비 상대적으로 큰 음수만 카운트.
        if len(volumes) > 0 and volumes.max() > 0:
            vol_threshold = -volumes.max() * 1e-6  # mean이 아닌 max 대비 1e-6
        else:
            vol_threshold = -1e-30
        negative_count = int(np.sum(volumes < vol_threshold))
        return volumes, negative_count

    # ------------------------------------------------------------------
    # Aspect ratio
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_max_aspect_ratio(
        points: np.ndarray,
        faces: list[list[int]],
        owner: np.ndarray,
        n_cells: int,
        n_internal: int,
    ) -> float:
        """Max aspect ratio across all cells (max_edge / min_edge per cell)."""
        if n_cells == 0:
            return 1.0

        # Build cell → set of vertex indices
        cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
        for fi, face in enumerate(faces):
            cell_id = int(owner[fi])
            if cell_id < n_cells:
                cell_verts[cell_id].update(face)

        max_ar = 1.0
        for cv in cell_verts:
            if len(cv) < 2:
                continue
            verts = points[list(cv)]
            # Compute all pairwise edge lengths
            n = len(verts)
            max_e = 0.0
            min_e = float("inf")
            for i in range(n):
                for j in range(i + 1, n):
                    d = float(np.linalg.norm(verts[i] - verts[j]))
                    if d > max_e:
                        max_e = d
                    if d < min_e:
                        min_e = d
            if min_e > 1e-30:
                ar = max_e / min_e
                if ar > max_ar:
                    max_ar = ar

        return max_ar

    # ------------------------------------------------------------------
    # Min determinant estimate
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_min_determinant(cell_volumes: np.ndarray) -> float:
        """Conservative determinant estimate from cell volume uniformity.

        The true min determinant requires full Jacobian computation for each
        cell, which is mesh-type-specific.  For tet meshes the determinant is
        proportional to the volume ratio.  We approximate it as:

            min_det ≈ min(volumes) / mean(volumes)

        clamped to [0, 1].
        """
        if len(cell_volumes) == 0:
            return 1.0
        mean_vol = float(cell_volumes.mean())
        if mean_vol <= 0:
            return 0.0
        min_vol = float(cell_volumes.min())
        if min_vol <= 0:
            return 0.0
        return float(np.clip(min_vol / mean_vol, 0.0, 1.0))

    # ------------------------------------------------------------------
    # neatmesh supplementary quality layer
    # ------------------------------------------------------------------

    @staticmethod
    def neatmesh_available() -> bool:
        """Return True if neatmesh is importable."""
        return _NEATMESH_AVAILABLE

    def run_neatmesh(self, mesh_file: Path) -> dict[str, Any]:
        """Compute supplementary quality metrics using neatmesh.

        neatmesh reads a meshio-compatible mesh file (VTK, Gmsh .msh, etc.)
        and returns additional statistics: non-orthogonality, adjacent cell
        volume ratio, face aspect ratios, and cell counts per type.

        Args:
            mesh_file: Path to a meshio-readable 3-D mesh file.

        Returns:
            Dictionary with neatmesh metrics, or an empty dict if neatmesh is
            not available or the mesh cannot be read.

        Example returned keys::

            {
                "max_non_ortho": float,
                "avg_non_ortho": float,
                "max_adj_volume_ratio": float,
                "max_face_aspect_ratio": float,
                "n_cells": int,
                "n_faces": int,
                "hex_count": int,
                "tetra_count": int,
                "wedge_count": int,
                "pyramid_count": int,
            }
        """
        if not _NEATMESH_AVAILABLE:
            log.debug("neatmesh not available — skipping supplementary metrics")
            return {}

        if not mesh_file.is_file():
            log.warning("run_neatmesh: file not found", path=str(mesh_file))
            return {}

        try:
            io_mesh = _meshio.read(str(mesh_file))
            reader = _NeatReader3D(io_mesh)
            analyzer = _NeatAnalyzer3D(reader)

            analyzer.count_cell_types()
            analyzer.analyze_faces()
            analyzer.analyze_cells()
            analyzer.analyze_non_ortho()
            analyzer.analyze_adjacents_volume_ratio()

            metrics: dict[str, Any] = {
                "n_cells": analyzer.n_cells,
                "n_faces": analyzer.n_faces,
                "hex_count": analyzer.hex_count,
                "tetra_count": analyzer.tetra_count,
                "wedge_count": analyzer.wedge_count,
                "pyramid_count": analyzer.pyramid_count,
            }

            if len(analyzer.non_ortho) > 0:
                metrics["max_non_ortho"] = float(analyzer.non_ortho.max())
                metrics["avg_non_ortho"] = float(analyzer.non_ortho.mean())

            if len(analyzer.adj_ratio) > 0:
                metrics["max_adj_volume_ratio"] = float(analyzer.adj_ratio.max())

            if len(analyzer.face_aspect_ratios) > 0:
                metrics["max_face_aspect_ratio"] = float(
                    analyzer.face_aspect_ratios.max()
                )

            log.info(
                "neatmesh supplementary metrics computed",
                n_cells=metrics.get("n_cells"),
                max_non_ortho=metrics.get("max_non_ortho"),
            )
            return metrics

        except Exception as exc:  # noqa: BLE001
            log.warning("neatmesh analysis failed", error=str(exc))
            return {}

    # ------------------------------------------------------------------
    # Fallback for empty/unreadable meshes
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> CheckMeshResult:
        return CheckMeshResult(
            cells=0,
            faces=0,
            points=0,
            max_non_orthogonality=0.0,
            avg_non_orthogonality=0.0,
            max_skewness=0.0,
            max_aspect_ratio=1.0,
            min_face_area=0.0,
            min_cell_volume=0.0,
            min_determinant=0.0,
            negative_volumes=0,
            severely_non_ortho_faces=0,
            failed_checks=0,
            mesh_ok=False,
        )
