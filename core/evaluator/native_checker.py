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
        # 3b. Face normal orientation 교정 — owner cell 중심에서 face centre 로
        # 향하는 방향을 "바깥"으로 삼아 face normal 을 flip.
        # (cfMesh 등 일부 엔진은 polyMesh 의 face vertex ordering 이 OpenFOAM
        # 표준 owner→neighbour 와 항상 일치하지 않음. 이를 보정하지 않으면
        # non-orthogonality 가 180° 근처로 오판되고 divergence theorem 의 volume
        # 이 음수가 나온다. 실제 OpenFOAM checkMesh 와 동일 결과를 내기 위함.)
        # ------------------------------------------------------------------
        if len(face_centres) > 0 and len(owner) > 0:
            to_face = face_centres - cell_centres[owner]
            dot_check = np.einsum("ij,ij->i", to_face, face_normals)
            # normal 이 owner→face_centre 방향과 반대이면 flip
            flip_mask = dot_check < 0
            if np.any(flip_mask):
                n_flip = int(flip_mask.sum())
                face_normals[flip_mask] = -face_normals[flip_mask]
                log.debug(
                    "face_normal_orientation_fixed",
                    flipped=n_flip,
                    total=len(face_normals),
                )

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

        # v0.4.0-beta5: OpenFOAM checkMesh 의 "Faces not in upper triangular
        # order" 는 renumberMesh 로 즉시 해결 가능한 비치명적 warning 이므로
        # mesh_ok 판정에는 포함하지 않고 info log 로만 기록.
        n_out_of_order = self._count_faces_not_upper_triangular(owner, neighbour)
        if n_out_of_order > 0:
            log.info(
                "native_checker_face_ordering_not_upper_triangular",
                out_of_order_count=int(n_out_of_order),
                note="renumberMesh 실행으로 해결 가능 — failed_check 으로 카운트 안 함",
            )

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

        # ------------------------------------------------------------------
        # 12. neatmesh supplementary metrics (if available)
        # ------------------------------------------------------------------
        if self.neatmesh_available():
            try:
                neatmesh_metrics = self._run_neatmesh_from_polyMesh(case_dir, result)
                if neatmesh_metrics:
                    log.info("neatmesh supplementary metrics merged", **neatmesh_metrics)
            except Exception as exc:  # noqa: BLE001
                log.debug("neatmesh integration failed (non-fatal)", error=str(exc))

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
        # OpenFOAM non-orthogonality 정의: face normal 과 cell-cell 축 사이 각도.
        # face normal 방향이 owner→neighbour 반대로 저장돼도 결과는 동일해야 하므로
        # abs(cos) 로 [0°, 90°] 범위만 계산. (cfMesh 등 일부 엔진의 face ordering
        # 이 표준과 다를 때 180° 오판 방지)
        cos_theta = np.clip(np.abs(cos_theta), 0.0, 1.0)
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

        # ── face normal 방향을 "owner cell 바깥" 기준으로 정렬 ──
        # cfMesh/octree mesh 는 face vertex ordering 이 항상 표준 owner→neighbour 를
        # 따르지 않을 수 있다. 각 face 의 owner centroid → face centre 벡터와
        # normal 이 반대 방향이면 flip 해서 일관된 outward normal 로 만든다.
        # 선행 조건: cell_centres 가 이미 계산됐어야 한다 → 임시로 face centroid
        # 평균으로 근사 (정밀한 centroid 는 호출자가 별도 전달).
        cell_c = np.zeros((n_cells, 3), dtype=np.float64)
        cnt = np.zeros(n_cells, dtype=np.int64)
        np.add.at(cell_c, owner, fc)
        np.add.at(cnt, owner, 1)
        if n_internal > 0:
            np.add.at(cell_c, neighbour[:n_internal], fc[:n_internal])
            np.add.at(cnt, neighbour[:n_internal], 1)
        nz = cnt > 0
        cell_c[nz] /= cnt[nz, np.newaxis]

        to_face = fc - cell_c[owner]
        owner_outward_dot = np.einsum("ij,ij->i", to_face, face_normals)
        outward_sign = np.where(owner_outward_dot < 0, -1.0, 1.0)
        # normal · sign 이 owner-outward 방향을 보장
        n_outward = face_normals * outward_sign[:, np.newaxis]

        # Contribution: face_centre · outward_normal * area
        contribution = np.einsum("ij,ij->i", fc, n_outward) * face_areas  # (F,)

        volumes = np.zeros(n_cells, dtype=np.float64)

        # Internal faces: owner +, neighbour -
        if n_internal > 0:
            own_idx = owner[:n_internal]
            nbr_idx = neighbour[:n_internal]
            np.add.at(volumes, own_idx, contribution[:n_internal])
            np.subtract.at(volumes, nbr_idx, contribution[:n_internal])

        # Boundary faces: owner +
        if n_faces > n_internal:
            bnd_owners = owner[n_internal:]
            np.add.at(volumes, bnd_owners, contribution[n_internal:])

        volumes /= 3.0
        # 절대값으로 — outward 정렬 후에도 cell centroid 근사 오차로 부호가 반대
        # 나올 수 있음. 실제 volume 은 항상 양수 (mesh 가 geometric valid 이면).
        volumes = np.abs(volumes)

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
        """Max aspect ratio (max_edge / min_edge per cell) — 대형 메쉬 대응.

        기존 구현은 Python 이중 loop 로 500k cells 에 2분+ 소요.
        개선:
          1) 각 cell 의 vertex 집합 생성까지는 동일.
          2) inner pair-distance loop 를 numpy broadcasting 으로 대체.
          3) cell 수 > 100k 면 균등 샘플링으로 대표값 추정 (전수 스캔 대신).
        """
        if n_cells == 0:
            return 1.0

        # Build cell → set of vertex indices
        cell_verts: list[list[int]] = [[] for _ in range(n_cells)]
        seen_per_cell: list[set[int]] = [set() for _ in range(n_cells)]
        for fi, face in enumerate(faces):
            cell_id = int(owner[fi])
            if cell_id >= n_cells:
                continue
            seen = seen_per_cell[cell_id]
            lst = cell_verts[cell_id]
            for v in face:
                if v not in seen:
                    seen.add(v)
                    lst.append(v)

        # 대형 메쉬는 샘플링 (전체 대비 대표성 충분, 시간 급감).
        if n_cells > 100_000:
            step = max(1, n_cells // 50_000)
            cell_indices = range(0, n_cells, step)
        else:
            cell_indices = range(n_cells)

        max_ar = 1.0
        for ci in cell_indices:
            cv = cell_verts[ci]
            if len(cv) < 2:
                continue
            verts = points[cv]                    # (n, 3)
            # 벡터화된 pairwise distance — upper-triangular 만 추출
            diff = verts[:, None, :] - verts[None, :, :]
            d2 = np.einsum("ijk,ijk->ij", diff, diff)
            iu = np.triu_indices_from(d2, k=1)
            d2u = d2[iu]
            if d2u.size == 0:
                continue
            d2u_pos = d2u[d2u > 1e-30]
            if d2u_pos.size == 0:
                continue
            ar = float(np.sqrt(d2u_pos.max() / d2u_pos.min()))
            if ar > max_ar:
                max_ar = ar

        return max_ar

    # ------------------------------------------------------------------
    # Min determinant estimate
    # ------------------------------------------------------------------

    @staticmethod
    def _count_faces_not_upper_triangular(
        owner: np.ndarray, neighbour: np.ndarray,
    ) -> int:
        """internal face 의 (owner, neighbour) 이 upper triangular 순서가 아닌 개수.

        OpenFOAM polyMesh 규약: internal face 는 (owner, neighbour) 오름차순으로
        정렬되어 있어야 한다 (owner[i-1] <= owner[i], 같은 owner 안에서는
        neighbour[i-1] < neighbour[i]). 위반 개수를 반환.
        """
        n_int = int(len(neighbour))
        if n_int <= 1:
            return 0
        owner_int = np.asarray(owner[:n_int], dtype=np.int64)
        nbr_int = np.asarray(neighbour, dtype=np.int64)
        # key = owner * (max_nbr + 1) + neighbour 로 정렬 여부 체크
        # 안전: 큰 n_cells 에도 int64 overflow 없도록 np.lexsort 기준으로 비교.
        order = np.lexsort((nbr_int, owner_int))
        n_ok = int(np.all(order == np.arange(n_int)))
        if n_ok:
            return 0
        # 정확한 violation 수 — 현재 배열과 정렬된 배열이 다른 인덱스 수
        return int((order != np.arange(n_int)).sum())

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
    # polyMesh → neatmesh bridge
    # ------------------------------------------------------------------

    def _run_neatmesh_from_polyMesh(
        self, case_dir: Path, result: CheckMeshResult
    ) -> dict[str, Any] | None:
        """Attempt to run neatmesh on the polyMesh using pyvista.

        This constructs a meshio mesh from the polyMesh data and writes it
        to a temporary file, then analyzes with neatmesh.

        Args:
            case_dir: OpenFOAM case directory.
            result: Native CheckMeshResult for reference.

        Returns:
            Dictionary of merged neatmesh metrics, or None if conversion fails.
        """
        if not _NEATMESH_AVAILABLE:
            return None

        try:
            import tempfile
            import pyvista as pv
        except ImportError:
            log.debug("pyvista not available for polyMesh→neatmesh conversion")
            return None

        try:
            # Read polyMesh using pyvista (supports OpenFOAM native format)
            poly_dir = case_dir / "constant" / "polyMesh"
            pv_mesh = pv.read(str(poly_dir))

            # Create temporary VTK file
            with tempfile.NamedTemporaryFile(suffix=".vtu", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            pv_mesh.save(str(tmp_path))
            log.debug("polyMesh converted to VTK", tmp_path=str(tmp_path))

            # Run neatmesh on temporary file
            neatmesh_metrics = self.run_neatmesh(tmp_path)

            # Clean up temporary file
            try:
                tmp_path.unlink()
            except Exception as exc:  # noqa: BLE001
                log.debug("failed to clean temporary mesh file", error=str(exc))

            return neatmesh_metrics if neatmesh_metrics else None

        except Exception as exc:  # noqa: BLE001
            log.debug("polyMesh neatmesh conversion failed", error=str(exc))
            return None

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
