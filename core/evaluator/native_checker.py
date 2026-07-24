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

import importlib
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np

from core.evaluator.poly_quality_metrics import compute_poly_phase0_metrics
from core.schemas import CheckMeshResult
from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels_array,
    parse_foam_points_array,
)

log = get_logger(__name__)

_NATIVE_METRICS: Any | None = None
_NATIVE_METRICS_IMPORT_ATTEMPTED = False


def _load_native_metrics() -> Any | None:
    """Load optional pybind11 geometry kernels for NativeMeshChecker.

    The extension is deliberately optional.  Source builds and CI can run with
    the pure-Python/NumPy implementation, while developer or release builds can
    place ``native_metrics*.so`` in ``auto_tessell_core/build`` or set
    ``AUTOTESSELL_EXT_BUILD_DIR``.
    """
    global _NATIVE_METRICS, _NATIVE_METRICS_IMPORT_ATTEMPTED
    if _NATIVE_METRICS_IMPORT_ATTEMPTED:
        return _NATIVE_METRICS
    _NATIVE_METRICS_IMPORT_ATTEMPTED = True

    candidate_dirs: list[Path] = []
    env_dir = os.environ.get("AUTOTESSELL_EXT_BUILD_DIR", "").strip()
    if env_dir:
        candidate_dirs.append(Path(env_dir))
    repo_root = Path(__file__).resolve().parents[2]
    candidate_dirs.append(repo_root / "auto_tessell_core" / "build")

    for candidate in candidate_dirs:
        if candidate.is_dir():
            candidate_s = str(candidate)
            if candidate_s not in sys.path:
                sys.path.insert(0, candidate_s)

    try:
        _NATIVE_METRICS = importlib.import_module("native_metrics")
    except Exception as exc:  # noqa: BLE001
        log.debug("native_metrics extension unavailable", error=str(exc))
        _NATIVE_METRICS = None
    return _NATIVE_METRICS

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

        points = parse_foam_points_array(points_file)
        native_metrics = _load_native_metrics()
        face_topology: Any | None = None
        raw_faces: list[list[int]] | None = None
        topology_parser = (
            getattr(native_metrics, "parse_foam_faces_topology_file", None)
            if native_metrics is not None
            else None
        )
        if topology_parser is not None:
            try:
                face_topology = topology_parser(faces_file)
            except Exception as exc:  # noqa: BLE001
                log.debug("native face topology parser failed", error=str(exc))
        if face_topology is None:
            raw_faces = parse_foam_faces(faces_file)

        def materialize_faces() -> list[list[int]]:
            nonlocal raw_faces
            if raw_faces is not None:
                return raw_faces
            assert face_topology is not None
            try:
                raw_faces = face_topology.to_lists()
            except Exception as exc:  # noqa: BLE001
                log.debug("native face topology materialization failed", error=str(exc))
                raw_faces = parse_foam_faces(faces_file)
            return raw_faces

        owner = parse_foam_labels_array(owner_file)
        neighbour = parse_foam_labels_array(neighbour_file)
        bnd_entries = parse_foam_boundary(boundary_file)

        n_faces = (
            int(face_topology.face_count) if face_topology is not None else len(raw_faces or ())
        )
        if points.size == 0 or n_faces == 0 or owner.size == 0:
            log.warning("Empty polyMesh — returning degenerate CheckMeshResult")
            return self._empty_result()

        # iter-0005 autoresearch (2026-05-15): polyMesh data-integrity fix.
        # cfMesh-style writers emit a `neighbour` list of length
        # len(faces) with `-1` as a sentinel for boundary faces.  The
        # OpenFOAM convention is len(neighbour) == nInternalFaces.
        # Using the cfMesh-style file directly causes:
        #   • cell_sum[neighbour[fi]] for fi >= n_internal → Python
        #     negative indexing → updates last-cell phantom centroid
        #   • phantom centroid spreads to cube center, producing fake
        #     87-90° non_orthogonality on the affected cell's real faces.
        # Authoritative source for nInternalFaces = minimum startFace
        # over all patches in `boundary`.  Strip the trailing entries.
        if bnd_entries:
            _min_start = min(int(p.get("startFace", n_faces))
                             for p in bnd_entries)
            if 0 < _min_start < neighbour.shape[0]:
                neighbour = neighbour[:_min_start]
        # Belt + suspenders: also drop any leading -1 sentinels that
        # survived (some pMesh writers put them at the front).
        if neighbour.size and (neighbour < 0).any():
            neighbour = neighbour[neighbour >= 0]

        n_points = len(points)
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
        if face_topology is not None:
            face_geometry = self._compute_face_geometry_topology(points, face_topology)
            if face_geometry is None:
                face_geometry = self._compute_face_geometry(points, materialize_faces())
        else:
            face_geometry = self._compute_face_geometry(points, materialize_faces())
        if face_geometry is not None:
            face_centres, face_normals, face_areas = face_geometry
        else:
            faces = materialize_faces()
            face_centres = self._compute_face_centres(points, faces)  # (F, 3)
            face_normals, face_areas = self._compute_face_normals_areas(points, faces)
        # face_normals: (F, 3) unit normals; face_areas: (F,) scalar areas

        # ------------------------------------------------------------------
        # 3. Cell centres
        # ------------------------------------------------------------------
        if face_topology is not None:
            combined_cell_metrics = self._compute_combined_cell_metrics_topology(
                points,
                face_topology,
                owner,
                n_cells,
                neighbour,
            )
            if combined_cell_metrics is None:
                combined_cell_metrics = self._compute_combined_cell_metrics(
                    points,
                    materialize_faces(),
                    owner,
                    n_cells,
                    neighbour,
                )
        else:
            combined_cell_metrics = self._compute_combined_cell_metrics(
                points,
                materialize_faces(),
                owner,
                n_cells,
                neighbour,
            )
        precomputed_aspect: tuple[np.ndarray, np.ndarray] | None = None
        if combined_cell_metrics is not None:
            cell_centres, aspect_cell_ids, aspect_ratios = combined_cell_metrics
            precomputed_aspect = (aspect_cell_ids, aspect_ratios)
        else:
            cell_centres = self._compute_cell_centres_from_vertices(
                points,
                materialize_faces(),
                owner,
                n_cells,
                neighbour,
            )  # (C, 3)

        # ------------------------------------------------------------------
        # 3b. Face normal orientation 교정 — owner cell 중심에서 face centre 로
        # 향하는 방향을 "바깥"으로 삼아 face normal 을 flip.
        # (cfMesh 등 일부 엔진은 polyMesh 의 face vertex ordering 이 OpenFOAM
        # 표준 owner→neighbour 와 항상 일치하지 않음. 이를 보정하지 않으면
        # non-orthogonality 가 180° 근처로 오판되고 divergence theorem 의 volume
        # 이 음수가 나온다. 실제 OpenFOAM checkMesh 와 동일 결과를 내기 위함.)
        # ------------------------------------------------------------------
        n_inverted_owner_cells = 0
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
            # Inversion detection — a cell whose every owned face had its raw
            # normal flipped is wound opposite to the OpenFOAM owner-outward
            # convention (a true topological inversion).  Skipped when the
            # global flip rate is high (≥50%): in that case the entire mesh
            # uses an inverse convention and the orientation fix already
            # normalised it, so per-cell "all flipped" is not a defect.
            n_face_total = max(int(len(flip_mask)), 1)
            global_flip_rate = float(int(flip_mask.sum())) / float(n_face_total)
            if global_flip_rate < 0.5 and n_cells > 0:
                flip_per_cell = np.zeros(n_cells, dtype=np.int64)
                faces_per_cell = np.zeros(n_cells, dtype=np.int64)
                valid_owner_mask = (owner >= 0) & (owner < n_cells)
                if np.any(valid_owner_mask):
                    np.add.at(
                        flip_per_cell,
                        owner[valid_owner_mask],
                        flip_mask[valid_owner_mask].astype(np.int64),
                    )
                    np.add.at(faces_per_cell, owner[valid_owner_mask], 1)
                fully_inverted = (
                    (faces_per_cell > 0)
                    & (flip_per_cell == faces_per_cell)
                    & (flip_per_cell > 0)
                )
                n_inverted_owner_cells = int(fully_inverted.sum())

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
        max_internal_skewness = float(max_skewness)
        max_boundary_skewness = self._compute_boundary_skewness(
            face_centres, face_normals, cell_centres, owner, n_internal
        )
        max_skewness = max(max_internal_skewness, max_boundary_skewness)

        # ------------------------------------------------------------------
        # 6. Cell volumes (signed divergence theorem)
        # ------------------------------------------------------------------
        cell_volumes, negative_volumes = self._compute_cell_volumes(
            points, raw_faces, face_normals, face_areas, owner, neighbour,
            n_cells, n_internal, cell_centres, face_centres
        )

        # ------------------------------------------------------------------
        # 7. Aspect ratios (per cell: max edge / min edge via face vertices)
        # ------------------------------------------------------------------
        if precomputed_aspect is not None:
            _, aspect_ratios = precomputed_aspect
            max_aspect_ratio = float(aspect_ratios.max()) if aspect_ratios.size else 1.0
        else:
            max_aspect_ratio = self._compute_max_aspect_ratio(
                points, materialize_faces(), owner, n_cells, n_internal
            )

        # ------------------------------------------------------------------
        # 8. Min face area
        # ------------------------------------------------------------------
        min_face_area = float(face_areas.min()) if len(face_areas) > 0 else 0.0
        if face_topology is not None and bool(face_topology.all_triangles):
            max_concavity, max_face_warpage = 0.0, 0.0
        else:
            max_concavity, max_face_warpage = self._compute_face_concavity_warpage(
                points, materialize_faces(), face_normals, face_areas, face_centres
            )
        (
            min_face_weight,
            min_vol_ratio,
            max_adjacent_volume_ratio,
            max_cell_size_growth_ratio,
        ) = self._compute_face_weight_volume_ratio(
            face_centres,
            face_normals * face_areas[:, np.newaxis],
            cell_centres,
            owner,
            neighbour,
            cell_volumes,
            n_internal,
        )

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
        # 10b. Phase 0 report-only FV/poly metrics
        # ------------------------------------------------------------------
        # These measurements intentionally do not feed any gate.  Materialize
        # topology faces only here, after the existing checker calculations,
        # so the report path remains compatible with the optional native
        # topology kernel and existing quality fields.
        phase0_metrics = compute_poly_phase0_metrics(
            points,
            materialize_faces(),
            owner,
            neighbour,
            n_internal,
            cell_centres,
            face_centres,
            face_normals,
            face_areas,
            cell_volumes,
        )

        # ------------------------------------------------------------------
        # 11. failed_checks / mesh_ok heuristic
        # ------------------------------------------------------------------
        # NativeMeshChecker는 OpenFOAM checkMesh의 "Failed N mesh checks"를
        # 모방한다. OpenFOAM은 negative volumes/zero volumes만 failed check으로
        # 카운트하고, non-ortho/skewness 등은 warning으로 처리한다.
        # Note: divergence theorem 볼륨 계산은 부동소수점 오차로 인해
        # 매우 작은 음수값(-1e-15 등)이 발생할 수 있다. 의미있는 negative volume
        # 검출을 위해 상대 임계값을 사용한다.
        # negative_volumes는 _compute_cell_volumes에서 이미 상대 tolerance로 카운트.
        # _compute_cell_volumes uses abs() pyramids for robust magnitudes (mixed
        # tet/prism meshes from cfMesh-style writers) so it cannot detect
        # inverted cells on its own; combine its tolerance count with the
        # orientation-fix-based inversion count tracked above.
        meaningful_neg_volumes = max(int(negative_volumes), int(n_inverted_owner_cells))

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
            max_boundary_skewness=float(max_boundary_skewness),
            max_internal_skewness=float(max_internal_skewness),
            max_concavity=float(max_concavity),
            min_face_weight=float(min_face_weight),
            min_vol_ratio=float(min_vol_ratio),
            max_adjacent_volume_ratio=float(max_adjacent_volume_ratio),
            max_face_warpage=float(max_face_warpage),
            # Adjacent volume jumps are reported explicitly above.  Do not also
            # export cube-root(volume ratio) as a linear expansion metric: that
            # double-counts the same check and over-penalizes anisotropic BL
            # prism stacks where volume is intentionally dominated by thickness.
            max_cell_size_growth_ratio=None,
            max_face_planar_deviation=phase0_metrics.max_face_planar_deviation,
            mean_face_planar_deviation=phase0_metrics.mean_face_planar_deviation,
            p95_face_planar_deviation=phase0_metrics.p95_face_planar_deviation,
            max_face_normal_spread_deg=phase0_metrics.max_face_normal_spread_deg,
            mean_face_normal_spread_deg=phase0_metrics.mean_face_normal_spread_deg,
            p95_face_normal_spread_deg=phase0_metrics.p95_face_normal_spread_deg,
            max_juretic_psi=phase0_metrics.max_juretic_psi,
            mean_juretic_psi=phase0_metrics.mean_juretic_psi,
            p95_juretic_psi=phase0_metrics.p95_juretic_psi,
            skewness_formula_audit=(
                "current gate: max(internal line-projection ratio, "
                "boundary tangential miss/normal distance); internal line-projection "
                "ratio is Juretic psi, boundary ratio is not"
            ),
            juretic_psi_definition="psi = |m|/|d|, m = face centre - line/face intersection",
            min_cell_h=phase0_metrics.min_cell_h,
            mean_cell_h=phase0_metrics.mean_cell_h,
            p95_cell_h=phase0_metrics.p95_cell_h,
            max_cell_h=phase0_metrics.max_cell_h,
            min_circle_ratio=phase0_metrics.min_circle_ratio,
            mean_circle_ratio=phase0_metrics.mean_circle_ratio,
            p95_circle_ratio=phase0_metrics.p95_circle_ratio,
            max_circle_ratio=phase0_metrics.max_circle_ratio,
            min_sphericity=phase0_metrics.min_sphericity,
            mean_sphericity=phase0_metrics.mean_sphericity,
            p95_sphericity=phase0_metrics.p95_sphericity,
            max_sphericity=phase0_metrics.max_sphericity,
            min_uniformity_factor=phase0_metrics.min_uniformity_factor,
            mean_uniformity_factor=phase0_metrics.mean_uniformity_factor,
            p95_uniformity_factor=phase0_metrics.p95_uniformity_factor,
            max_uniformity_factor=phase0_metrics.max_uniformity_factor,
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
    def _compute_face_geometry_topology(
        points: np.ndarray, topology: Any
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Return face geometry directly from native flat topology storage."""
        native_metrics = _load_native_metrics()
        if native_metrics is None:
            return None
        kernel = getattr(native_metrics, "compute_face_geometry_topology", None)
        if kernel is None:
            return None
        try:
            centres, normals, areas = kernel(points, topology)
            return (
                np.asarray(centres, dtype=np.float64),
                np.asarray(normals, dtype=np.float64),
                np.asarray(areas, dtype=np.float64),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("native topology face geometry failed", error=str(exc))
            return None

    @staticmethod
    def _compute_face_geometry(
        points: np.ndarray, faces: list[list[int]]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Return face centres/normals/areas through the optional C++ kernel."""
        native_metrics = _load_native_metrics()
        if native_metrics is None:
            return None
        try:
            centres, normals, areas = native_metrics.compute_face_geometry(points, faces)
            return (
                np.asarray(centres, dtype=np.float64),
                np.asarray(normals, dtype=np.float64),
                np.asarray(areas, dtype=np.float64),
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("native_metrics.compute_face_geometry failed", error=str(exc))
            return None

    @staticmethod
    def _compute_face_centres(
        points: np.ndarray, faces: list[list[int]]
    ) -> np.ndarray:
        """Return (F, 3) array of face centres (average of vertices).

        Vectorized: group faces by vertex count → stack (G, K, 3) → mean(axis=1).
        Falls back to scalar loop only for face groups too small to batch.
        """
        n = len(faces)
        centres = np.empty((n, 3), dtype=np.float64)
        if n == 0:
            return centres

        # Group face indices by vertex count
        from collections import defaultdict
        groups: dict[int, list[int]] = defaultdict(list)
        for i, face in enumerate(faces):
            groups[len(face)].append(i)

        for k, idxs in groups.items():
            idx_arr = np.asarray(idxs, dtype=np.int64)
            G = len(idxs)
            # Build (G, k) vertex index array — vectorized via flat list + reshape
            vidx = np.fromiter(
                (v for i in idxs for v in faces[i]), dtype=np.int64, count=G * k
            ).reshape(G, k)
            # points[vidx]: (G, k, 3) → mean over axis=1 → (G, 3)
            centres[idx_arr] = points[vidx].mean(axis=1)

        return centres

    @staticmethod
    def _compute_face_normals_areas(
        points: np.ndarray, faces: list[list[int]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return unit normals (F, 3) and areas (F,) using fan triangulation.

        Vectorized: group by vertex count → stack (G, K, 3) → fan cross products.
        """
        n = len(faces)
        normals = np.zeros((n, 3), dtype=np.float64)
        areas = np.zeros(n, dtype=np.float64)
        if n == 0:
            return normals, areas

        from collections import defaultdict
        groups: dict[int, list[int]] = defaultdict(list)
        for i, face in enumerate(faces):
            if len(face) >= 3:
                groups[len(face)].append(i)

        for k, idxs in groups.items():
            idx_arr = np.asarray(idxs, dtype=np.int64)
            G = len(idxs)
            # Build (G, k) vertex index array — vectorized via flat list + reshape
            vidx = np.fromiter(
                (v for i in idxs for v in faces[i]), dtype=np.int64, count=G * k
            ).reshape(G, k)
            verts = points[vidx]  # (G, k, 3)
            v0 = verts[:, 0:1, :]  # (G, 1, 3)
            # Fan triangulation: edges from v0 to v1..v_{k-1} and v2..v_k
            e1 = verts[:, 1:-1, :] - v0   # (G, k-2, 3)
            e2 = verts[:, 2:, :] - v0     # (G, k-2, 3)
            # Cross products for each triangle: (G, k-2, 3)
            crosses = np.cross(e1, e2)
            # Sum over triangles → (G, 3)
            area_vec = crosses.sum(axis=1)
            mag = np.linalg.norm(area_vec, axis=1)  # (G,)
            areas[idx_arr] = mag * 0.5
            nonzero = mag > 0.0
            normals[idx_arr[nonzero]] = area_vec[nonzero] / mag[nonzero, np.newaxis]

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

    @staticmethod
    def _compute_cell_centres_from_vertices(
        points: np.ndarray,
        faces: list[list[int]],
        owner: np.ndarray,
        n_cells: int,
        neighbour: np.ndarray | None = None,
    ) -> np.ndarray:
        """Return cell centres as the mean of unique vertices per cell.

        Boundary-layer cells are mostly prisms and general polyhedra.  The old
        unweighted face-centre mean can bias centres toward split side faces,
        inflating non-orthogonality, skewness, and face-weight estimates.  A
        unique-vertex mean is still inexpensive, but tracks the geometric centre
        of prism-like cells more closely.
        """
        if n_cells <= 0:
            return np.zeros((0, 3), dtype=np.float64)
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                centres = native_metrics.compute_cell_centres_from_vertices(
                    points, faces, owner, neighbour, int(n_cells)
                )
                return np.asarray(centres, dtype=np.float64)
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "native_metrics.compute_cell_centres_from_vertices failed",
                    error=str(exc),
                )
        cell_vertices: list[set[int]] = [set() for _ in range(n_cells)]
        n_internal = len(neighbour) if neighbour is not None else 0
        for face_i, face in enumerate(faces):
            if not face:
                continue
            own = int(owner[face_i]) if face_i < len(owner) else -1
            if 0 <= own < n_cells:
                cell_vertices[own].update(int(v) for v in face)
            if face_i < n_internal and neighbour is not None:
                nbr = int(neighbour[face_i])
                if 0 <= nbr < n_cells:
                    cell_vertices[nbr].update(int(v) for v in face)

        centres = np.zeros((n_cells, 3), dtype=np.float64)
        for cell_i, verts in enumerate(cell_vertices):
            if not verts:
                continue
            idx = np.fromiter(verts, dtype=np.int64)
            valid = (idx >= 0) & (idx < len(points))
            if np.any(valid):
                centres[cell_i] = points[idx[valid]].mean(axis=0)
        return centres

    @staticmethod
    def _compute_combined_cell_metrics(
        points: np.ndarray,
        faces: list[list[int]],
        owner: np.ndarray,
        n_cells: int,
        neighbour: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Return native cell centres and sampled aspect ratios in one pass."""
        native_metrics = _load_native_metrics()
        if native_metrics is None:
            return None
        kernel = getattr(native_metrics, "compute_cell_centres_and_aspect_ratios", None)
        if kernel is None:
            return None

        try:
            result = kernel(points, faces, owner, neighbour, int(n_cells))
            return NativeMeshChecker._validate_combined_cell_metrics(result, n_cells)
        except Exception as exc:  # noqa: BLE001
            log.debug(
                "native_metrics.compute_cell_centres_and_aspect_ratios failed",
                error=str(exc),
            )
            return None

    @staticmethod
    def _compute_combined_cell_metrics_topology(
        points: np.ndarray,
        topology: Any,
        owner: np.ndarray,
        n_cells: int,
        neighbour: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        """Return combined metrics directly from native flat topology."""
        native_metrics = _load_native_metrics()
        if native_metrics is None:
            return None
        kernel = getattr(
            native_metrics,
            "compute_cell_centres_and_aspect_ratios_topology",
            None,
        )
        if kernel is None:
            return None
        try:
            result = kernel(points, topology, owner, neighbour, int(n_cells))
            return NativeMeshChecker._validate_combined_cell_metrics(result, n_cells)
        except Exception as exc:  # noqa: BLE001
            log.debug("native topology combined cell metrics failed", error=str(exc))
            return None

    @staticmethod
    def _validate_combined_cell_metrics(
        result: Any,
        n_cells: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        centres, cell_ids, aspect_ratios = result
        centres_array = np.asarray(centres, dtype=np.float64)
        cell_ids_array = np.asarray(cell_ids, dtype=np.int64)
        aspect_array = np.asarray(aspect_ratios, dtype=np.float64)
        if centres_array.shape != (n_cells, 3):
            raise ValueError("combined native cell centres have invalid shape")
        if cell_ids_array.ndim != 1 or aspect_array.ndim != 1:
            raise ValueError("combined native aspect arrays must be one-dimensional")
        if cell_ids_array.size != aspect_array.size:
            raise ValueError("combined native aspect arrays have different lengths")
        return centres_array, cell_ids_array, aspect_array

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
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                max_non_ortho, avg_non_ortho, severe_count = (
                    native_metrics.compute_non_orthogonality(
                        face_centres,
                        face_normals,
                        cell_centres,
                        owner,
                        neighbour,
                        int(n_internal),
                        float(self.SEVERE_NON_ORTHO_THRESHOLD),
                    )
                )
                return (
                    float(max_non_ortho),
                    float(avg_non_ortho),
                    int(severe_count),
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("native_metrics.compute_non_orthogonality failed", error=str(exc))

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
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                return float(
                    native_metrics.compute_skewness(
                        face_centres,
                        cell_centres,
                        owner,
                        neighbour,
                        int(n_internal),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("native_metrics.compute_skewness failed", error=str(exc))

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

    @staticmethod
    def _compute_boundary_skewness(
        face_centres: np.ndarray,
        face_normals: np.ndarray,
        cell_centres: np.ndarray,
        owner: np.ndarray,
        n_internal: int,
    ) -> float:
        """Approximate OpenFOAM boundary-face skewness.

        For a good boundary face, the owner-cell centre projected along the
        face normal lands near the face centre.  The normalized tangential miss
        gives a scale-free boundary skewness estimate.
        """
        if len(face_centres) <= n_internal:
            return 0.0
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                return float(
                    native_metrics.compute_boundary_skewness(
                        face_centres,
                        face_normals,
                        cell_centres,
                        owner,
                        int(n_internal),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("native_metrics.compute_boundary_skewness failed", error=str(exc))
        b_idx = np.arange(n_internal, len(face_centres), dtype=np.int64)
        if b_idx.size == 0:
            return 0.0
        own = owner[b_idx]
        valid = (own >= 0) & (own < len(cell_centres))
        if not np.any(valid):
            return 0.0
        b_idx = b_idx[valid]
        own = own[valid]
        fc = face_centres[b_idx]
        cc = cell_centres[own]
        n = face_normals[b_idx]
        n_mag = np.linalg.norm(n, axis=1)
        valid_n = n_mag > 1e-30
        if not np.any(valid_n):
            return 0.0
        fc = fc[valid_n]
        cc = cc[valid_n]
        n = n[valid_n] / n_mag[valid_n, np.newaxis]
        to_face = fc - cc
        normal_dist = np.einsum("ij,ij->i", to_face, n)
        proj = cc + normal_dist[:, np.newaxis] * n
        denom = np.maximum(np.abs(normal_dist), 1e-30)
        skew = np.linalg.norm(fc - proj, axis=1) / denom
        if skew.size == 0:
            return 0.0
        return float(np.nanmax(skew))

    @staticmethod
    def _compute_face_concavity_warpage(
        points: np.ndarray,
        faces: list[list[int]],
        face_normals: np.ndarray,
        face_areas: np.ndarray,
        face_centres: np.ndarray,
    ) -> tuple[float, float]:
        """Return max concavity degrees and max warpage ratio.

        The warpage estimate mirrors OpenFOAM faceFlatness: compare the
        magnitude of the polygon area vector with the sum of triangle area
        magnitudes around the face centre.  Warpage is exported as
        ``1 - flatness`` so planar faces are zero.
        """
        max_concavity = 0.0
        max_warpage = 0.0
        for facei, face in enumerate(faces):
            if len(face) < 3:
                max_warpage = max(max_warpage, 1.0)
                continue
            if len(face) > 3:
                verts = points[np.asarray(face, dtype=np.int64)]
                fc = face_centres[facei]
                sum_a = 0.0
                for i in range(len(face)):
                    a = verts[i]
                    b = verts[(i + 1) % len(face)]
                    tri_n = 0.5 * np.cross(b - a, fc - a)
                    sum_a += float(np.linalg.norm(tri_n))
                if sum_a > 1e-30:
                    flatness = float(face_areas[facei]) / sum_a
                    max_warpage = max(max_warpage, max(0.0, 1.0 - flatness))

                n = face_normals[facei]
                n_norm = float(np.linalg.norm(n))
                if n_norm > 1e-30:
                    n = n / n_norm
                    signs: list[float] = []
                    for i in range(len(face)):
                        prev_p = verts[(i - 1) % len(face)]
                        cur_p = verts[i]
                        next_p = verts[(i + 1) % len(face)]
                        cross = np.cross(cur_p - prev_p, next_p - cur_p)
                        s = float(np.dot(cross, n))
                        if abs(s) > 1e-14:
                            signs.append(s)
                    if signs:
                        ref = 1.0 if sum(1 for s in signs if s >= 0.0) >= len(signs) / 2 else -1.0
                        if any(s * ref < -1e-14 for s in signs):
                            # OpenFOAM reports face concavity in degrees.  A
                            # sign reversal is already over the accepted 80 deg
                            # gate, so use a conservative hard-fail value.
                            max_concavity = max(max_concavity, 180.0)
        return float(max_concavity), float(max_warpage)

    @staticmethod
    def _compute_face_weight_volume_ratio(
        face_centres: np.ndarray,
        face_area_vectors: np.ndarray,
        cell_centres: np.ndarray,
        owner: np.ndarray,
        neighbour: np.ndarray,
        cell_volumes: np.ndarray,
        n_internal: int,
    ) -> tuple[float, float, float, float]:
        """Compute OpenFOAM-style interpolation weight and volume-ratio stats."""
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                result = native_metrics.compute_face_weight_volume_ratio(
                    face_centres,
                    face_area_vectors,
                    cell_centres,
                    owner,
                    neighbour,
                    cell_volumes,
                    n_internal,
                )
                min_weight, min_ratio, max_ratio, max_growth = result
                return (
                    float(min_weight),
                    float(min_ratio),
                    float(max_ratio),
                    float(max_growth),
                )
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "native face weight/volume ratio kernel failed",
                    error=str(exc),
                )
        if n_internal <= 0 or len(cell_volumes) == 0:
            return 1.0, 1.0, 1.0, 1.0
        own = owner[:n_internal]
        nbr = neighbour[:n_internal]
        valid = (
            (own >= 0)
            & (nbr >= 0)
            & (own < len(cell_centres))
            & (nbr < len(cell_centres))
            & (own < len(cell_volumes))
            & (nbr < len(cell_volumes))
        )
        if not np.any(valid):
            return 1.0, 1.0, 1.0, 1.0
        own = own[valid]
        nbr = nbr[valid]
        fc = face_centres[:n_internal][valid]
        fa = face_area_vectors[:n_internal][valid]
        co = cell_centres[own]
        cn = cell_centres[nbr]
        # OpenFOAM meshCheck::faceWeights:
        # dOwn = mag(faceArea & (faceCentre - ownerCentre))
        # dNei = mag(faceArea & (neighbourCentre - faceCentre))
        # weight = min(dOwn, dNei)/(dOwn + dNei + VSMALL)
        d_own = np.abs(np.einsum("ij,ij->i", fa, fc - co))
        d_nei = np.abs(np.einsum("ij,ij->i", fa, cn - fc))
        denom = d_own + d_nei
        valid_w = denom > 1e-300
        if np.any(valid_w):
            weights = np.minimum(d_own[valid_w], d_nei[valid_w]) / denom[valid_w]
            min_face_weight = float(np.nanmin(weights)) if weights.size else 1.0
        else:
            min_face_weight = 1.0

        vo = np.abs(cell_volumes[own])
        vn = np.abs(cell_volumes[nbr])
        valid_v = (vo > 1e-30) & (vn > 1e-30)
        if not np.any(valid_v):
            return min_face_weight, 0.0, float("inf"), float("inf")
        ratios = np.maximum(vo[valid_v], vn[valid_v]) / np.maximum(
            np.minimum(vo[valid_v], vn[valid_v]),
            1e-30,
        )
        max_adjacent = float(np.nanmax(ratios)) if ratios.size else 1.0
        min_vol_ratio = float(1.0 / max(max_adjacent, 1.0))
        max_growth = float(max_adjacent ** (1.0 / 3.0))
        return min_face_weight, min_vol_ratio, max_adjacent, max_growth

    # ------------------------------------------------------------------
    # Cell volumes (divergence theorem)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_cell_volumes(
        points: np.ndarray,
        faces: list[list[int]] | None,
        face_normals: np.ndarray,
        face_areas: np.ndarray,
        owner: np.ndarray,
        neighbour: np.ndarray,
        n_cells: int,
        n_internal: int,
        cell_centres: np.ndarray | None = None,
        face_centres: np.ndarray | None = None,
    ) -> tuple[np.ndarray, int]:
        """Estimate cell volumes from face pyramids around each cell centre.

        OpenFOAM's geometric checks reason about owner/neighbour face pyramids.
        Summing ``abs(faceAreaVector dot (faceCentre - cellCentre)) / 3`` over
        the faces incident to each cell is origin-independent and is robust to
        mixed tet/prism meshes whose face winding is not perfectly consistent.
        """
        if n_cells <= 0:
            return np.zeros(0, dtype=np.float64), 0

        if face_centres is None:
            if faces is None:
                raise ValueError("faces required when face centres are not precomputed")
            fc = NativeMeshChecker._compute_face_centres(points, faces)
        else:
            fc = face_centres
        area_vecs = face_normals * face_areas[:, np.newaxis]
        if cell_centres is None or len(cell_centres) != n_cells:
            if faces is None:
                raise ValueError("faces required when cell centres are not precomputed")
            cell_centres = NativeMeshChecker._compute_cell_centres_from_vertices(
                points, faces, owner, n_cells, neighbour,
            )
        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                volumes, negative_count = native_metrics.compute_cell_volumes(
                    fc,
                    face_normals,
                    face_areas,
                    cell_centres,
                    owner,
                    neighbour,
                    int(n_cells),
                    int(n_internal),
                )
                return np.asarray(volumes, dtype=np.float64), int(negative_count)
            except Exception as exc:  # noqa: BLE001
                log.debug("native_metrics.compute_cell_volumes failed", error=str(exc))

        volumes = np.zeros(n_cells, dtype=np.float64)
        n_faces = len(fc)
        own_arr = np.asarray(owner, dtype=np.int64)
        n_owner_use = min(n_faces, own_arr.shape[0])
        if n_owner_use > 0:
            own_slice = own_arr[:n_owner_use]
            valid_own = (own_slice >= 0) & (own_slice < n_cells)
            if np.any(valid_own):
                idx = np.nonzero(valid_own)[0]
                own_idx = own_slice[idx]
                pyr_own = np.abs(
                    np.einsum(
                        "ij,ij->i",
                        area_vecs[idx],
                        fc[idx] - cell_centres[own_idx],
                    )
                ) / 3.0
                np.add.at(volumes, own_idx, pyr_own)
        n_int_use = min(n_internal, n_owner_use)
        if n_int_use > 0:
            nbr_arr = np.asarray(neighbour[:n_int_use], dtype=np.int64)
            valid_nbr = (nbr_arr >= 0) & (nbr_arr < n_cells)
            if np.any(valid_nbr):
                idx_n = np.nonzero(valid_nbr)[0]
                nbr_idx = nbr_arr[idx_n]
                pyr_nbr = np.abs(
                    np.einsum(
                        "ij,ij->i",
                        area_vecs[idx_n],
                        fc[idx_n] - cell_centres[nbr_idx],
                    )
                ) / 3.0
                np.add.at(volumes, nbr_idx, pyr_nbr)

        negative_count = 0
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
        """Max aspect ratio across cells — see ``_per_cell_aspect_ratios``."""
        _, ars = NativeMeshChecker._per_cell_aspect_ratios(
            points, faces, owner, n_cells, n_internal,
        )
        return float(ars.max()) if ars.size else 1.0

    @staticmethod
    def _per_cell_aspect_ratios(
        points: np.ndarray,
        faces: list[list[int]],
        owner: np.ndarray,
        n_cells: int,
        n_internal: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-(sampled)-cell aspect ratio (max_edge / min_edge per cell).

        대형 메쉬 대응: 기존 구현은 Python 이중 loop 로 500k cells 에 2분+ 소요.
        개선:
          1) 각 cell 의 vertex 집합 생성까지는 동일.
          2) inner pair-distance loop 를 numpy broadcasting 으로 대체.
          3) cell 수 > 100k 면 균등 샘플링으로 대표값 추정 (전수 스캔 대신).

        Returns ``(cell_ids, aspect_ratios)`` — ``cell_ids`` are the (possibly
        sampled) cell indices the ratios correspond to, so a caller can map
        ratios back to owner faces / colour a colormap. ``_compute_max_aspect_ratio``
        (mesh-wide PASS/FAIL gate) just takes ``.max()`` of this — kept as a
        thin wrapper so the two never drift apart.
        """
        if n_cells == 0:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

        native_metrics = _load_native_metrics()
        if native_metrics is not None:
            try:
                cell_ids, aspect_ratios = native_metrics.compute_per_cell_aspect_ratios(
                    points, faces, owner, int(n_cells)
                )
                return (
                    np.asarray(cell_ids, dtype=np.int64),
                    np.asarray(aspect_ratios, dtype=np.float64),
                )
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "native_metrics.compute_per_cell_aspect_ratios failed",
                    error=str(exc),
                )

        # ── Build cell → vertex list using CSR-style vectorized scatter ──
        # Flatten all face vertex indices alongside their owner cell ids.
        # For boundary faces the owner array covers all faces; internal faces
        # also have a neighbour — but for vertex collection owner is enough
        # (each vertex appears via at least one face per cell).
        flat_verts: list[int] = []
        flat_cells: list[int] = []
        for fi, face in enumerate(faces):
            cell_id = int(owner[fi])
            if cell_id >= n_cells:
                continue
            for v in face:
                flat_verts.append(v)
                flat_cells.append(cell_id)

        if not flat_verts:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

        flat_verts_arr = np.asarray(flat_verts, dtype=np.int64)
        flat_cells_arr = np.asarray(flat_cells, dtype=np.int64)

        # Sort by (cell, vertex) and deduplicate — vectorized
        sort_key = flat_cells_arr * (flat_verts_arr.max() + 1) + flat_verts_arr
        order = np.argsort(sort_key, kind="stable")
        sc = flat_cells_arr[order]
        sv = flat_verts_arr[order]
        # Remove (cell, vertex) duplicates
        uniq_mask = np.empty(len(sc), dtype=bool)
        uniq_mask[0] = True
        uniq_mask[1:] = (sc[1:] != sc[:-1]) | (sv[1:] != sv[:-1])
        sc = sc[uniq_mask]
        sv = sv[uniq_mask]

        # Build CSR offsets: for each cell, the slice [csr_ptr[c]:csr_ptr[c+1]]
        # gives its unique vertex indices.
        cell_counts = np.bincount(sc, minlength=n_cells)  # (n_cells,)
        csr_ptr = np.empty(n_cells + 1, dtype=np.int64)
        csr_ptr[0] = 0
        np.cumsum(cell_counts, out=csr_ptr[1:])

        # 대형 메쉬는 샘플링 (전체 대비 대표성 충분, 시간 급감). 이 per-cell
        # 파이썬 루프는 셀당 numpy 오버헤드가 커서 ~70k 셀이면 30초+ 걸린다 —
        # 상한을 두어 평가가 멈추는 것처럼 보이지 않게 한다 (max-aspect 추정치).
        _AR_SAMPLE_CAP = 25_000
        if n_cells > _AR_SAMPLE_CAP:
            step = max(1, n_cells // _AR_SAMPLE_CAP)
            cell_indices_arr = np.arange(0, n_cells, step, dtype=np.int64)
        else:
            cell_indices_arr = np.arange(n_cells, dtype=np.int64)

        out_cells: list[int] = []
        out_ars: list[float] = []
        for ci in cell_indices_arr:
            start, end = int(csr_ptr[ci]), int(csr_ptr[ci + 1])
            if end - start < 2:
                continue
            cv = sv[start:end]
            verts = points[cv]                    # (n, 3)
            # Vectorized pairwise distance — upper-triangular only
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
            out_cells.append(int(ci))
            out_ars.append(ar)

        if not out_ars:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)
        return np.asarray(out_cells, dtype=np.int64), np.asarray(out_ars, dtype=np.float64)

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
        native_metrics = _load_native_metrics()
        kernel = (
            getattr(native_metrics, "count_faces_not_upper_triangular", None)
            if native_metrics is not None
            else None
        )
        if kernel is not None:
            try:
                return int(kernel(owner, neighbour))
            except Exception as exc:  # noqa: BLE001
                log.debug(
                    "native_metrics.count_faces_not_upper_triangular failed",
                    error=str(exc),
                )
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
