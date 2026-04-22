"""poly 메쉬용 BL: native_bl 결과를 polyhedral-friendly 형태로 유지.

전략:
    1. native_bl.generate_native_bl() 로 wall 근처 prism (wedge) 층을 삽입.
       prism cell 은 polyMesh 포맷에서 face-list 로 정의되므로 OpenFOAM 의
       polyhedral cell type 과 호환된다 (wedge = 2 triangle + 3 quad, 5 face).
    2. bulk (내부 tet) 영역을 polyDualMesh 로 dual 변환 — OpenFOAM 사용 가능 시.
       사용 불가 시엔 native_bl 결과 그대로 반환 (tet + prism 혼합).
    3. 결과 polyMesh 는 "wall 근처 prism (polyhedral-compatible) + bulk 는
       tet 또는 polyDual" 구조.

이는 ANSYS Fluent / Star-CCM+ 등에서 쓰는 "polyhedral + prism BL" 의
표준 패턴.

Phase 2 확장 (향후):
    - bulk tet → 자체 dual 변환 구현 (scipy Voronoi 의존 제거)
    - prism vs polyhedral cell 간 face 정렬 품질 개선
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from core.layers.native_bl import BLConfig, generate_native_bl
from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class PolyBLResult:
    success: bool
    elapsed: float
    n_prism_cells: int = 0
    bulk_dual_applied: bool = False
    message: str = ""


def _try_openfoam_poly_dual(
    case_dir: Path, feature_angle: float = 30.0,
) -> tuple[bool, str]:
    """OpenFOAM polyDualMesh 로 bulk 를 dual 변환 시도 (가용한 경우).

    polyDualMesh 는 wall 근처 prism 을 건드리지 않도록 featureAngle 로 각도
    제약 하에 tet → polyhedral dual 을 생성한다. BL 보존을 위해
    featureAngle 을 낮춰 wall boundary edge 가 보존되도록 한다.
    """
    try:
        from core.utils.openfoam_utils import run_openfoam  # noqa: PLC0415
    except Exception as exc:
        return False, f"openfoam_utils import 실패: {exc}"

    try:
        run_openfoam(
            "polyDualMesh",
            case_dir,
            args=[str(feature_angle), "-overwrite"],
        )
        return True, f"polyDualMesh (featureAngle={feature_angle}) OK"
    except FileNotFoundError as exc:
        return False, f"openfoam_missing: {exc}"
    except Exception as exc:
        return False, f"polyDualMesh 실패: {str(exc)[-200:]}"


def run_poly_bl_transition(
    case_dir: Path,
    *,
    num_layers: int,
    growth_ratio: float,
    first_thickness: float,
    wall_patch_names: list[str] | None = None,
    backup_original: bool = True,
    max_total_ratio: float = 0.3,
    apply_bulk_dual: bool = True,
    dual_feature_angle: float = 30.0,
) -> PolyBLResult:
    """poly 메쉬용 BL 삽입 + (옵션) bulk dual 변환.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        num_layers/growth_ratio/first_thickness: BL 파라미터.
        apply_bulk_dual: True 이면 OpenFOAM polyDualMesh 로 bulk 를 dual 변환.
            False 이면 prism + tet 혼합 메쉬 그대로 반환.
        dual_feature_angle: polyDualMesh featureAngle (BL 을 보존하려면 낮게).

    Returns:
        PolyBLResult.
    """
    t0 = time.perf_counter()
    cfg = BLConfig(
        num_layers=int(num_layers),
        growth_ratio=float(growth_ratio),
        first_thickness=float(first_thickness),
        wall_patch_names=wall_patch_names,
        backup_original=backup_original,
        max_total_ratio=float(max_total_ratio),
    )
    bl_res = generate_native_bl(case_dir, cfg)
    if not bl_res.success:
        return PolyBLResult(
            success=False, elapsed=time.perf_counter() - t0,
            message=f"native_bl 실패: {bl_res.message}",
        )

    bulk_dual_applied = False
    dual_msg = ""
    if apply_bulk_dual:
        ok, dual_msg = _try_openfoam_poly_dual(case_dir, dual_feature_angle)
        bulk_dual_applied = ok
        if not ok:
            log.info("poly_bl_bulk_dual_skipped", reason=dual_msg)

    elapsed = time.perf_counter() - t0
    return PolyBLResult(
        success=True,
        elapsed=elapsed,
        n_prism_cells=int(bl_res.n_prism_cells),
        bulk_dual_applied=bulk_dual_applied,
        message=(
            f"poly_bl_transition OK — prism={bl_res.n_prism_cells}, "
            f"bulk_dual={bulk_dual_applied}. "
            + (f"dual: {dual_msg}" if apply_bulk_dual else "dual skipped")
        ),
    )
