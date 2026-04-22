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


def _try_native_poly_dual(case_dir: Path) -> tuple[bool, str]:
    """v0.4 native: polyMesh 에서 tet array 를 복원해 tet_to_poly_dual 로 변환.

    OpenFOAM polyDualMesh 호출 없이 순수 Python. case_dir 의 polyMesh 가 **전체
    tet cell** 로 구성되어 있어야 함 (이 함수는 native_bl 후 bulk 부분만 대상).
    """
    try:
        import numpy as np  # noqa: PLC0415
        from core.generator.native_poly.dual import tet_to_poly_dual  # noqa: PLC0415
        from core.utils.polymesh_reader import (  # noqa: PLC0415
            parse_foam_faces, parse_foam_labels, parse_foam_points,
        )
    except Exception as exc:
        return False, f"native dual import 실패: {exc}"

    poly_dir = case_dir / "constant" / "polyMesh"
    try:
        pts = np.array(parse_foam_points(poly_dir / "points"), dtype=np.float64)
        faces = parse_foam_faces(poly_dir / "faces")
        owner = np.array(parse_foam_labels(poly_dir / "owner"), dtype=np.int64)
        neighbour = np.array(
            parse_foam_labels(poly_dir / "neighbour"), dtype=np.int64,
        )
    except Exception as exc:
        return False, f"polyMesh 읽기 실패: {exc}"

    n_cells = (int(owner.max()) + 1) if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    if n_cells == 0:
        return False, "cell 없음"

    # 각 cell 에 속한 face vertex 들을 모아 unique vertex set 으로 tet 추출.
    # 4 vertex cell 만 tet 으로 인정, 그 외 (prism 등) 은 제외 후 dual 변환 불가.
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        cell_verts[int(owner[fi])].update(int(v) for v in f)
        if fi < len(neighbour):
            cell_verts[int(neighbour[fi])].update(int(v) for v in f)
    tets: list[tuple[int, int, int, int]] = []
    n_non_tet = 0
    for cv in cell_verts:
        if len(cv) == 4:
            tets.append(tuple(sorted(cv)))    # type: ignore[arg-type]
        else:
            n_non_tet += 1
    if not tets:
        return False, (
            f"tet cell 0 — 입력 mesh 는 순수 tet 이어야 함 (non-tet={n_non_tet})"
        )
    if n_non_tet > 0:
        # prism 등 혼합 mesh 는 지원 안 함 → 실패
        return False, (
            f"혼합 mesh (non-tet={n_non_tet}) — native dual 은 순수 tet 만 지원"
        )
    T = np.array(tets, dtype=np.int64)
    res = tet_to_poly_dual(pts, T, case_dir)
    if not res.success:
        return False, f"native tet_to_poly_dual 실패: {res.message}"
    return True, f"native tet→poly dual OK ({res.message})"


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
        # v0.4: OpenFOAM polyDualMesh 대신 자체 구현 tet→poly dual 사용.
        # dual_feature_angle 은 현재 native 경로에서 사용 안 함 (호환용으로 유지).
        ok, dual_msg = _try_native_poly_dual(case_dir)
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
