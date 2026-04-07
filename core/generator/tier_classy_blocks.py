"""Tier classy_blocks: 구조 Hex 메쉬 생성기.

Fine 품질 레벨의 구조적 Hex 경로. classy_blocks로 blockMeshDict를 생성하고
OpenFOAM blockMesh를 실행한다. OpenFOAM이 없으면 gracefully skip한다.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_classy_blocks"


def _write_block_mesh_dict_via_classy(
    strategy: MeshStrategy,
    case_dir: Path,
) -> None:
    """classy_blocks로 blockMeshDict를 생성하고 system/ 디렉터리에 쓴다.

    Args:
        strategy: 메쉬 전략 (domain 정보 포함).
        case_dir: OpenFOAM 케이스 디렉터리.
    """
    import classy_blocks  # type: ignore[import-untyped]

    domain = strategy.domain
    x_min, y_min, z_min = domain.min
    x_max, y_max, z_max = domain.max
    cell_size = domain.base_cell_size

    nx = max(1, int(round((x_max - x_min) / cell_size)))
    ny = max(1, int(round((y_max - y_min) / cell_size)))
    nz = max(1, int(round((z_max - z_min) / cell_size)))

    logger.info(
        "classy_blocks_domain",
        min=domain.min,
        max=domain.max,
        cells=(nx, ny, nz),
    )

    # classy_blocks Mesh 생성
    mesh = classy_blocks.Mesh()

    # 단일 Box 블록 정의 (8개 꼭짓점 순서: OpenFOAM 규약)
    import numpy as np

    p000 = np.array([x_min, y_min, z_min])
    p100 = np.array([x_max, y_min, z_min])
    p110 = np.array([x_max, y_max, z_min])
    p010 = np.array([x_min, y_max, z_min])
    p001 = np.array([x_min, y_min, z_max])
    p101 = np.array([x_max, y_min, z_max])
    p111 = np.array([x_max, y_max, z_max])
    p011 = np.array([x_min, y_max, z_max])

    block = classy_blocks.Box(p000, p111)
    block.chop(0, count=nx)
    block.chop(1, count=ny)
    block.chop(2, count=nz)
    mesh.add(block)

    # blockMeshDict 파일 출력
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    bmd_path = system_dir / "blockMeshDict"

    mesh.write(str(bmd_path))
    logger.info("classy_blocks_bmd_written", path=str(bmd_path))


class TierClassyBlocksGenerator:
    """classy_blocks 기반 구조 Hex 메쉬 생성기.

    Fine 품질 레벨 구조 Hex 경로. classy_blocks로 blockMeshDict를 생성하고
    OpenFOAM blockMesh를 실행한다. OpenFOAM 미설치 시 gracefully skip.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """classy_blocks → blockMesh 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로 (참조용).
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier_classy_blocks_start")

        # classy_blocks import 시도
        try:
            import classy_blocks  # noqa: F401
        except (ImportError, AttributeError) as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_classy_blocks_import_failed",
                error=str(exc),
                hint="classy_blocks 미설치. pip install classy-blocks",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"classy_blocks 모듈 import 실패: {exc}. pip install classy-blocks",
            )

        # OpenFOAM blockMesh 존재 확인
        block_mesh_bin = shutil.which("blockMesh")
        if block_mesh_bin is None:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_classy_blocks_no_openfoam",
                hint="blockMesh 미설치 — OpenFOAM이 필요합니다.",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message="blockMesh 실행 파일을 찾을 수 없습니다. OpenFOAM 설치 필요.",
            )

        try:
            # blockMeshDict 생성
            _write_block_mesh_dict_via_classy(strategy, case_dir)

            # OpenFOAM blockMesh 실행
            from core.utils.openfoam_utils import run_openfoam

            run_openfoam("blockMesh", case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier_classy_blocks_success", elapsed=elapsed)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_classy_blocks_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"classy_blocks/blockMesh 실행 실패: {exc}",
            )
