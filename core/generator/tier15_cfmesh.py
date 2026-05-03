"""Tier 1.5: cfMesh cartesianMesh 메쉬 생성기."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from core.generator.openfoam_writer import OpenFOAMWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger
from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier15_cfmesh"


def generate_cfmesh_dict(strategy: MeshStrategy) -> dict[str, Any]:
    """cfMesh용 meshDict 내용을 Python dict로 생성한다.

    Args:
        strategy: 메쉬 전략 (surface_mesh, boundary_layers, tier_specific_params 포함).

    Returns:
        meshDict 구조를 담은 dict. surfaceFile/maxCellSize 키를 포함한다.
    """
    params = strategy.tier_specific_params
    sm = strategy.surface_mesh
    bl = strategy.boundary_layers

    # maxCellSize: tier_specific_params 우선, 없으면 target_cell_size * 4
    max_cell_size = params.get(
        "cfmesh_max_cell_size",
        sm.target_cell_size * 4,
    )

    result: dict[str, Any] = {
        "surfaceFile": "constant/triSurface/surface.stl",
        "maxCellSize": max_cell_size,
        "minCellSize": sm.min_cell_size,
        "boundaryCellSize": sm.target_cell_size,
    }

    if bl.enabled:
        result["boundaryLayers"] = {
            "nLayers": bl.num_layers,
            "thicknessRatio": bl.growth_ratio,
            "maxFirstLayerThickness": bl.first_layer_thickness,
            "optimiseLayer": 1,
        }

    # 추가 cfMesh 파라미터
    if "cfmesh_surface_refinement" in params:
        result["surfaceMeshRefinement"] = params["cfmesh_surface_refinement"]

    if "cfmesh_local_refinement" in params:
        result["localRefinement"] = params["cfmesh_local_refinement"]

    return result


class Tier15CfMeshGenerator:
    """cfMesh cartesianMesh 기반 Hex-dominant 메쉬 생성기.

    Tier 1 snappyHexMesh보다 설정이 단순하고 robust하다.
    cfMesh(cartesianMesh)가 설치된 OpenFOAM 환경 필요.
    """

    def __init__(self) -> None:
        self._writer = OpenFOAMWriter()

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 1.5 cfMesh 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier15_cfmesh_start", case_dir=str(case_dir))

        try:
            # 케이스 구조 생성
            self._writer.ensure_case_structure(case_dir)

            # STL 복사
            surface_stl = case_dir / "constant" / "triSurface" / "surface.stl"
            if preprocessed_path.exists():
                shutil.copy(str(preprocessed_path), str(surface_stl))
                logger.info("stl_copied", src=str(preprocessed_path), dst=str(surface_stl))

            # Dict 파일 생성
            self._writer.write_control_dict(case_dir, application="cartesianMesh")
            self._writer.write_fv_schemes(case_dir)
            self._writer.write_fv_solution(case_dir)

            cf_dict = generate_cfmesh_dict(strategy)
            mesh_dict_path = case_dir / "system" / "meshDict"
            self._writer.write_foam_dict(
                mesh_dict_path,
                cf_dict,
                location="system",
                object_name="meshDict",
            )

            # cartesianMesh 실행
            # BETA2844 — vendored cfMesh module 우선 (외부 OpenFOAM 의존 제거).
            # auto_tessell_core/build/cfmesh_native.so 가 빌드되어 있으면 그쪽을
            # 호출. 실패 시 시스템 OpenFOAM 의 run_openfoam() 으로 fallback.
            t_step = time.monotonic()
            _used_vendored = False
            try:
                import sys as _sys
                from pathlib import Path as _P
                _build = _P(__file__).resolve().parents[2] / "auto_tessell_core" / "build"
                if str(_build) not in _sys.path:
                    _sys.path.insert(0, str(_build))
                import cfmesh_native as _cfm  # type: ignore
                # surface STL path: case/constant/triSurface/<filename>
                _stl_dir = case_dir / "constant" / "triSurface"
                _stls = list(_stl_dir.glob("*.stl")) + list(_stl_dir.glob("*.STL"))
                if _stls:
                    # BETA2846 — STL 형상 보존 위해 boundary_cell_size,
                    # min_cell_size, BL 옵션 모두 propagate.
                    _params = strategy.tier_specific_params or {}
                    _sm = strategy.surface_mesh
                    _bl = getattr(strategy, "boundary_layers", None)
                    _target = float(getattr(_sm, "target_cell_size", 0.0) or 0.0) if _sm else 0.0
                    _min_sm = float(getattr(_sm, "min_cell_size", 0.0) or 0.0) if _sm else 0.0
                    _max = float(_params.get(
                        "cfmesh_max_cell_size",
                        _target * 4 if _target > 0 else 0.2,
                    ))
                    _bnd = float(_params.get(
                        "cfmesh_boundary_cell_size", _target,
                    ))
                    _min = float(_params.get(
                        "cfmesh_min_cell_size", _min_sm,
                    ))
                    _nL = 0; _tr = 1.2; _mf = 0.0
                    if _bl and getattr(_bl, "enabled", False):
                        _nL = int(getattr(_bl, "num_layers", 0) or 0)
                        _tr = float(getattr(_bl, "growth_ratio", 1.2) or 1.2)
                        _mf = float(getattr(_bl, "first_layer_thickness", 0.0) or 0.0)
                    # BETA2847 — GUI cfMesh BL widget override.
                    if "cfmesh_bl_n_layers" in _params:
                        _nL = int(_params["cfmesh_bl_n_layers"])
                    if "cfmesh_bl_thickness_ratio" in _params:
                        _tr = float(_params["cfmesh_bl_thickness_ratio"])
                    if "cfmesh_bl_max_first_layer" in _params:
                        _mf = float(_params["cfmesh_bl_max_first_layer"])
                    _r = _cfm.cartesian_mesh(
                        str(_stls[0]), str(case_dir),
                        max_cell_size=_max,
                        min_cell_size=_min,
                        boundary_cell_size=_bnd,
                        bl_n_layers=_nL,
                        bl_thickness_ratio=_tr,
                        bl_max_first_layer=_mf,
                        feature_angle_deg=float(
                            _params.get("bl_feature_angle", 30.0)
                        ),
                        keep_cells_intersecting_boundary=True,
                    )
                    if _r.get("success"):
                        _used_vendored = True
                        logger.info("cfmesh_vendored_used",
                                    polymesh=_r.get("polymesh_dir"),
                                    max=_max, bnd=_bnd, min=_min)
            except Exception as _exc:
                logger.debug("cfmesh_vendored_skipped", error=str(_exc)[:120])
            try:
                if not _used_vendored:
                    run_openfoam("cartesianMesh", case_dir)
            except OpenFOAMError as exc:
                step_elapsed = time.monotonic() - t_step
                elapsed = time.monotonic() - t_start
                logger.warning("cfmesh_cartesianmesh_failed", error=str(exc))
                from core.schemas import GeneratorStep
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    steps=[
                        GeneratorStep(
                            name="cartesianMesh",
                            status="failed",
                            time=step_elapsed,
                        )
                    ],
                    error_message=f"cartesianMesh 실패: {exc}",
                )

            step_elapsed = time.monotonic() - t_step
            elapsed = time.monotonic() - t_start

            logger.info("tier15_cfmesh_success", elapsed=elapsed)

            from core.schemas import GeneratorStep
            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
                steps=[
                    GeneratorStep(
                        name="cartesianMesh",
                        status="success",
                        time=step_elapsed,
                    )
                ],
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier15_cfmesh_unexpected_error", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 1.5 예상치 못한 오류: {exc}",
            )
