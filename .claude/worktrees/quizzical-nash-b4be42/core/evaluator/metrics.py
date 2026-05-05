"""pyvista/meshio 기반 추가 정량 지표 계산."""

from __future__ import annotations

from pathlib import Path

from core.schemas import AdditionalMetrics, BoundaryLayerStats, CellVolumeStats
from core.utils.logging import get_logger

log = get_logger(__name__)


class AdditionalMetricsComputer:
    """추가 정량 지표(셀 크기 분포, 경계층 통계)를 다중 경로로 계산한다.

    1. ofpp + polyMesh 직접 파싱 (OpenFOAM 불필요, 가장 빠름)
    2. foamToVTK + pyvista 변환 (OpenFOAM 필요)
    3. 모든 경로 실패 시 빈 AdditionalMetrics 반환 (예외 비전파)
    """

    def compute(self, case_dir: Path) -> AdditionalMetrics:  # noqa: C901
        """추가 정량 지표를 계산한다.

        Args:
            case_dir: OpenFOAM case 디렉터리 경로.

        Returns:
            AdditionalMetrics 객체 (계산 실패 시 빈 객체 반환).
        """
        try:
            return self._compute_internal(case_dir)
        except ImportError:
            log.warning("pyvista 미설치 — AdditionalMetrics 생략")
            return AdditionalMetrics()
        except Exception as exc:  # noqa: BLE001
            log.warning("AdditionalMetrics 계산 실패 (무시)", error=str(exc))
            return AdditionalMetrics()

    # ------------------------------------------------------------------

    def _compute_internal(self, case_dir: Path) -> AdditionalMetrics:
        # Strategy 1: ofpp (polyMesh 직접 파싱, OpenFOAM/PyVista 불필요)
        # PyVista/VTK는 GUI 백그라운드 스레드에서 concurrent하게 호출하면 SIGSEGV를
        # 유발하므로 (X11/VTK global state 비thread-safe), Strategy 2를 비활성화한다.
        try:
            metrics = self._compute_from_polymesh(case_dir)
            if metrics is not None:
                log.debug("AdditionalMetrics computed via ofpp (no OpenFOAM)")
                return metrics
        except Exception as exc:  # noqa: BLE001
            log.debug("ofpp polyMesh parsing failed", error=str(exc))

        log.debug("AdditionalMetrics 생략 — ofpp 파싱 실패, PyVista fallback 비활성화")
        return AdditionalMetrics()

    def _compute_from_polymesh(self, case_dir: Path) -> AdditionalMetrics | None:
        """ofpp를 사용하여 polyMesh에서 직접 추가 메트릭 계산.

        OpenFOAM 설치 없이 polyMesh를 파싱하여 셀 크기 분포 등을 계산한다.

        Args:
            case_dir: OpenFOAM case directory.

        Returns:
            AdditionalMetrics 또는 계산 불가 시 None.
        """
        try:
            from core.utils.polymesh_reader import load_polymesh_with_ofpp
            import numpy as np  # noqa: PLC0415

            foam_mesh = load_polymesh_with_ofpp(case_dir)
            if foam_mesh is None:
                return None

            # polyMesh의 owner/neighbour/faces로부터 셀 부피 추정
            # foam_mesh.volumes가 있으면 사용, 없으면 근사
            if hasattr(foam_mesh, 'volumes') and foam_mesh.volumes is not None:
                volumes = np.array(foam_mesh.volumes, dtype=np.float64)
            else:
                # Fallback: 근사값 계산 (사용 불가면 None 반환)
                return None

            if len(volumes) == 0:
                return None

            min_vol = float(volumes.min())
            max_vol = float(volumes.max())
            mean_vol = float(volumes.mean())
            std_vol = float(volumes.std())
            ratio = max_vol / max(abs(min_vol), 1e-30) if min_vol != 0 else float("inf")

            cell_volume_stats = CellVolumeStats(
                min=min_vol,
                max=max_vol,
                mean=mean_vol,
                std=std_vol,
                ratio_max_min=ratio,
            )

            # BL 상태 확인
            bl_enabled = self._check_bl_enabled(case_dir)
            bl_stats = self._compute_bl_stats_from_volumes(volumes, bl_enabled)

            return AdditionalMetrics(
                cell_volume_stats=cell_volume_stats,
                boundary_layer=bl_stats,
            )

        except ImportError:
            log.debug("ofpp not available for polyMesh parsing")
            return None
        except Exception as exc:  # noqa: BLE001
            log.debug("polymesh parsing with ofpp failed", error=str(exc))
            return None

    @staticmethod
    def _compute_bl_stats_from_volumes(
        volumes: object, bl_enabled: bool = True
    ) -> BoundaryLayerStats | None:
        """셀 부피 배열로부터 BL 통계를 추정한다."""
        try:
            import numpy as np  # noqa: PLC0415

            volumes = np.asarray(volumes, dtype=np.float64)
            heights = np.cbrt(np.abs(volumes))

            # BL이 비활성화된 경우만 정확히 알 수 있음 (coverage = 0.0)
            # 활성화된 경우 실제 BL 감지 불가능하므로 None 반환 (판정 skip)
            if not bl_enabled:
                return BoundaryLayerStats(
                    bl_coverage_percent=0.0,
                    avg_first_layer_height=float(heights.mean()),
                    min_first_layer_height=float(heights.min()),
                    max_first_layer_height=float(heights.max()),
                )
            else:
                # BL enabled이지만 실제 감지 불가능 → None 반환
                return None

        except Exception:  # noqa: BLE001
            return None

    def _run_foam_to_vtk(self, case_dir: Path) -> None:
        try:
            from core.utils.openfoam_utils import run_openfoam
            run_openfoam("foamToVTK", case_dir)
            log.debug("foamToVTK 완료")
        except Exception as exc:
            log.warning("foamToVTK 실패", error=str(exc))

    def _find_vtk_file(self, vtk_dir: Path) -> Path | None:
        if not vtk_dir.exists():
            return None
        # foamToVTK outputs .vtk (legacy) or .vtm/.vtu (modern)
        candidates = sorted(
            vtk_dir.glob("**/*.vtk")
        ) or sorted(
            vtk_dir.glob("**/*.vtu")
        ) or sorted(
            vtk_dir.glob("**/*.vtm")
        )
        if not candidates:
            return None
        # 타임스텝 0 (또는 가장 이른 파일) 우선
        return candidates[0]

    def _check_bl_enabled(self, case_dir: Path) -> bool:
        """mesh_strategy.json에서 BL enabled 상태를 확인한다."""
        try:
            import json  # noqa: PLC0415
            strategy_file = case_dir / "mesh_strategy.json"
            if not strategy_file.exists():
                return False
            with open(strategy_file) as f:
                data = json.load(f)
            # boundary_layer.enabled 확인
            bl_cfg = data.get("boundary_layer", {})
            return bool(bl_cfg.get("enabled", False))
        except Exception:  # noqa: BLE001
            return False

    def _compute_bl_stats(self, mesh: object, bl_enabled: bool = True) -> BoundaryLayerStats | None:
        """경계층 통계를 추정한다. pyvista mesh 객체를 받는다."""
        try:
            import numpy as np  # noqa: PLC0415
            import pyvista as pv  # noqa: PLC0415

            assert isinstance(mesh, pv.DataSet)
            # 벽면 패치의 첫 번째 레이어 높이를 근사적으로 계산
            # polyMesh에서 정확한 BL 검출은 foamToVTK 이후 별도 field 필요
            # 여기서는 표면 근처 셀 크기의 큐브루트를 첫 레이어 높이 근사값으로 사용
            cell_sizes = mesh.compute_cell_sizes(volume=True, length=False, area=False)
            vols = cell_sizes["Volume"]
            heights = np.cbrt(np.abs(vols))

            # BL이 비활성화된 경우만 정확히 알 수 있음 (coverage = 0.0)
            # 활성화된 경우 실제 BL 감지 불가능하므로 None 반환 (판정 skip)
            if not bl_enabled:
                return BoundaryLayerStats(
                    bl_coverage_percent=0.0,
                    avg_first_layer_height=float(heights.mean()),
                    min_first_layer_height=float(heights.min()),
                    max_first_layer_height=float(heights.max()),
                )
            else:
                # BL enabled이지만 실제 감지 불가능 → None 반환
                return None

        except Exception:  # noqa: BLE001
            return None


def tet_mean_ratio_quality(pts: object, tets: object) -> float:
    """Compute mean-ratio quality (worst) for all tets.

    Args:
        pts: (n_pts, 3) array of tet vertices.
        tets: (n_tets, 4) array of tet indices.

    Returns:
        Worst (minimum) mean-ratio quality across all tets.
    """
    import numpy as np  # noqa: PLC0415

    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int32)

    if len(tets) == 0:
        return 1.0

    # Vectorized: gather all tet vertices at once — shape (n_tets, 4, 3)
    v = pts[tets]  # (N, 4, 3)
    a, b, c, d = v[:, 0], v[:, 1], v[:, 2], v[:, 3]
    e0, e1, e2 = b - a, c - a, d - a  # (N, 3) each

    # Signed volume × 6 via scalar triple product
    cross_e1_e2 = np.cross(e1, e2)  # (N, 3)
    vol6 = np.einsum("ij,ij->i", e0, cross_e1_e2)  # (N,)
    vol = np.abs(vol6) / 6.0  # (N,)

    # Sum of squared edge lengths (6 edges per tet)
    l_sq = (
        np.einsum("ij,ij->i", e0, e0)
        + np.einsum("ij,ij->i", e1, e1)
        + np.einsum("ij,ij->i", e2, e2)
        + np.einsum("ij,ij->i", b - c, b - c)
        + np.einsum("ij,ij->i", b - d, b - d)
        + np.einsum("ij,ij->i", c - d, c - d)
    )  # (N,)

    degenerate = (np.abs(vol6) < 1e-30) | (l_sq < 1e-30)
    mr = np.where(
        degenerate,
        0.0,
        12.0 * (3.0 * vol) ** (2.0 / 3.0) / l_sq,
    )
    qualities = np.clip(mr, 0.0, 1.0)
    return float(np.min(qualities))
