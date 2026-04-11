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
        import pyvista as pv  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        # Strategy 1: Try ofpp (polyMesh 직접 파싱, OpenFOAM 불필요)
        try:
            metrics = self._compute_from_polymesh(case_dir)
            if metrics is not None:
                log.debug("AdditionalMetrics computed via ofpp (no OpenFOAM)")
                return metrics
        except Exception as exc:  # noqa: BLE001
            log.debug("ofpp polyMesh parsing failed", error=str(exc))

        # Strategy 2: Fall back to foamToVTK + pyvista
        vtk_dir = case_dir / "VTK"
        if not vtk_dir.exists():
            self._run_foam_to_vtk(case_dir)

        vtk_file = self._find_vtk_file(vtk_dir)
        if vtk_file is None:
            log.warning("VTK 파일 없음 — AdditionalMetrics 생략")
            return AdditionalMetrics()

        mesh = pv.read(str(vtk_file))
        cell_sizes = mesh.compute_cell_sizes(volume=True, length=False, area=False)
        volumes = cell_sizes["Volume"]

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

        # BL 검사: 벽면 경계 근처 셀 높이 추정
        bl_enabled = self._check_bl_enabled(case_dir)
        bl_stats = self._compute_bl_stats(mesh, bl_enabled)

        return AdditionalMetrics(
            cell_volume_stats=cell_volume_stats,
            boundary_layer=bl_stats,
        )

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
