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


def _classify_cells_by_vertex_count(
    owner, neighbour, faces,
) -> tuple[int, list[set[int]], list[int], list[int]]:
    """polyMesh face/owner/neighbour 로부터 각 cell 의 unique vertex set 복원.

    Returns:
        (n_cells, cell_verts, tet_cell_ids, non_tet_cell_ids).
        - cell_verts[ci] = cell ci 를 구성하는 vertex index set.
        - tet_cell_ids: 4 unique vertex (= tet) cell 인덱스 목록.
        - non_tet_cell_ids: 그 외 (prism 6, hex 8, polyhedron n) 인덱스 목록.
    """
    n_cells = int(owner.max()) + 1 if len(owner) else 0
    if len(neighbour):
        n_cells = max(n_cells, int(neighbour.max()) + 1)
    cell_verts: list[set[int]] = [set() for _ in range(n_cells)]
    for fi, f in enumerate(faces):
        cell_verts[int(owner[fi])].update(int(v) for v in f)
        if fi < len(neighbour):
            cell_verts[int(neighbour[fi])].update(int(v) for v in f)
    tet_ids: list[int] = []
    non_tet_ids: list[int] = []
    for ci, cv in enumerate(cell_verts):
        if len(cv) == 4:
            tet_ids.append(ci)
        else:
            non_tet_ids.append(ci)
    return n_cells, cell_verts, tet_ids, non_tet_ids


def _try_native_poly_dual(case_dir: Path) -> tuple[bool, str]:
    """v0.4 native: polyMesh 에서 tet array 를 복원해 tet_to_poly_dual 로 변환.

    OpenFOAM polyDualMesh 호출 없이 순수 Python.

    지원 케이스:
        - **전체 tet** polyMesh: 표준 dual 변환 → 완전 polyhedral mesh.
        - **hybrid (tet + prism)** polyMesh: prism BL 층이 섞여 있는 경우 dual 변환
          을 건너뛰고 원본 hybrid mesh 를 그대로 보존한다 (pass-through). 이때
          ``(True, "…hybrid preserved")`` 가 아닌 ``(False, …)`` 를 반환해 호출측이
          ``bulk_dual_applied=False`` 로 기록. mesh 자체는 여전히 valid polyMesh.

    완전한 hybrid dual (tet 부분만 polyhedral 로 변환하면서 prism 과 interface
    stitching 까지 수행) 은 beta15+ 로드맵. 현재는 prism 과 dual cell 사이 interface
    face 토폴로지 불일치 (prism 삼각형 vs dual 폴리곤) 문제 때문에 dual 을 skip.
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

    n_cells, cell_verts, tet_ids, non_tet_ids = _classify_cells_by_vertex_count(
        owner, neighbour, faces,
    )
    if n_cells == 0:
        return False, "cell 없음"

    n_tets = len(tet_ids)
    n_non_tet = len(non_tet_ids)

    if n_tets == 0:
        return False, f"tet cell 0 — dual 변환 불가 (non-tet={n_non_tet})"

    if n_non_tet > 0:
        # Hybrid (tet + prism) — dual 을 skip 하고 원본 mesh 보존.
        # interface stitching (prism outer triangle ↔ dual polygon 정합) 은 beta15+.
        log.info(
            "poly_bl_hybrid_pass_through",
            n_tets=n_tets,
            n_non_tet=n_non_tet,
            message="hybrid mesh preserved — full hybrid dual deferred",
        )
        return False, (
            f"hybrid mesh preserved (tet={n_tets}, non-tet={n_non_tet}) — "
            "full hybrid dual deferred to beta15+ roadmap"
        )

    # 순수 tet → 전체 dual 변환
    tets_list: list[tuple[int, int, int, int]] = [
        tuple(sorted(cell_verts[ci])) for ci in tet_ids  # type: ignore[misc]
    ]
    T = np.array(tets_list, dtype=np.int64)
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
