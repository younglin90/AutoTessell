"""Polyhedral mesh 변환기.

Tet mesh → Polyhedral dual mesh 변환.
OpenFOAM polyDualMesh 또는 자체 듀얼 변환을 사용한다.
"""

from __future__ import annotations

from pathlib import Path

from core.utils.logging import get_logger

log = get_logger(__name__)


def convert_to_polyhedral(
    case_dir: Path,
    feature_angle: float = 5.0,
    concave_multi_cells: bool = True,
) -> bool:
    """polyMesh를 폴리헤드럴 듀얼 메쉬로 변환한다.

    OpenFOAM polyDualMesh를 사용하여 tet/hex mesh를 폴리헤드럴로 변환.
    원본 polyMesh는 백업 후 덮어쓴다.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        feature_angle: 특징 보존 각도 [도]. 작을수록 더 많은 특징 보존.
        concave_multi_cells: True이면 오목 경계 셀을 분할.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    poly_dir = case_dir / "constant" / "polyMesh"
    if not poly_dir.exists():
        log.warning("polyhedral_no_polymesh", case_dir=str(case_dir))
        return False

    # 1. OpenFOAM polyDualMesh 시도
    try:
        from core.utils.openfoam_utils import run_openfoam

        args = [str(feature_angle)]
        if concave_multi_cells:
            args.append("-concaveMultiCells")
        args.append("-overwrite")

        log.info("polyDualMesh_start", feature_angle=feature_angle,
                 concave=concave_multi_cells)

        run_openfoam("polyDualMesh", case_dir, args=args)

        log.info("polyDualMesh_success")
        return True

    except FileNotFoundError:
        log.info("polyDualMesh_not_available", hint="OpenFOAM 미설치")
        return _convert_native(case_dir)

    except Exception as exc:
        log.warning("polyDualMesh_failed", error=str(exc))
        return False


def _convert_native(case_dir: Path) -> bool:
    """Python 네이티브 tet → poly 듀얼 변환 (OpenFOAM 없이).

    알고리즘:
    - 각 tet의 정점이 하나의 폴리헤드럴 셀이 됨
    - 각 tet이 하나의 듀얼 정점이 됨 (tet 중심)
    - 각 tet의 면(삼각형)이 듀얼 면의 일부가 됨

    Returns:
        True if succeeded.
    """
    try:
        import numpy as np

        from core.utils.polymesh_reader import (
            parse_foam_faces,
            parse_foam_labels,
            parse_foam_points,
        )

        poly_dir = case_dir / "constant" / "polyMesh"
        points = np.array(parse_foam_points(poly_dir / "points"))
        faces = parse_foam_faces(poly_dir / "faces")
        owner = np.array(parse_foam_labels(poly_dir / "owner"))
        neighbour = np.array(parse_foam_labels(poly_dir / "neighbour"))

        if len(points) == 0 or len(faces) == 0:
            return False

        n_internal = len(neighbour)
        max_cell = int(owner.max())
        if n_internal > 0:
            max_cell = max(max_cell, int(neighbour.max()))
        n_cells = max_cell + 1
        n_points = len(points)

        log.info("native_dual_start", n_cells=n_cells, n_points=n_points, n_faces=len(faces))

        # 듀얼 정점 = 원래 셀의 중심점
        # 듀얼 셀 = 원래 정점 주변의 셀 집합
        # 이것은 완전한 듀얼 변환이 아닌 간소화 버전

        # 셀 중심 계산
        cell_centres = np.zeros((n_cells, 3))
        cell_counts = np.zeros(n_cells)
        face_centres = np.array([points[f].mean(axis=0) for f in faces])

        np.add.at(cell_centres, owner, face_centres)
        np.add.at(cell_counts, owner, 1)
        if n_internal > 0:
            np.add.at(cell_centres, neighbour, face_centres[:n_internal])
            np.add.at(cell_counts, neighbour, 1)
        nonzero = cell_counts > 0
        cell_centres[nonzero] /= cell_counts[nonzero, np.newaxis]

        log.info("native_dual_done",
                 hint="Native tet→poly 변환은 제한적. OpenFOAM polyDualMesh 권장.")
        # 전체 구현은 복잡 — 현재는 로그만 남기고 원본 유지
        return False

    except Exception as exc:
        log.warning("native_dual_failed", error=str(exc))
        return False


def is_polyhedral_available() -> bool:
    """polyDualMesh가 사용 가능한지 확인."""
    try:
        from core.utils.openfoam_utils import _find_openfoam_bashrc
        return _find_openfoam_bashrc() is not None
    except Exception:
        return False
