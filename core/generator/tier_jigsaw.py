"""Tier JIGSAW: 비구조 tet 메쉬 생성기.

Draft 품질 레벨에서 TetWild 실패 시 fallback으로 사용한다.
jigsawpy로 3D 비구조 tet 메쉬를 생성한다.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_jigsaw"


class TierJigsawGenerator:
    """JIGSAW 기반 비구조 tet 메쉬 생성기.

    Draft 품질 레벨에서 TetWild 실패 시 fallback.
    jigsawpy.cmd.jigsaw()로 빠른 비구조 테트라헤드라이제이션을 수행한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """JIGSAW 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier_jigsaw_start", preprocessed_path=str(preprocessed_path))

        # jigsawpy import 시도
        try:
            import jigsawpy  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_jigsaw_import_failed",
                error=str(exc),
                hint="jigsawpy 미설치. pip install jigsawpy",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="jigsawpy",
                    fallback="다른 tier로 fallback",
                    action="pip install jigsawpy",
                    detail=str(exc),
                ),
            )

        # 파일 존재 확인
        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            import jigsawpy
            import numpy as np

            params = strategy.tier_specific_params
            hmax = params.get(
                "jigsaw_hmax",
                strategy.surface_mesh.target_cell_size,
            )
            hmin = params.get(
                "jigsaw_hmin",
                strategy.surface_mesh.min_cell_size,
            )

            logger.info(
                "tier_jigsaw_meshing",
                hmax=hmax,
                hmin=hmin,
            )

            # 작업 디렉터리 준비
            jig_work_dir = case_dir / "_jigsaw_work"
            jig_work_dir.mkdir(parents=True, exist_ok=True)

            geom_file = jig_work_dir / "geom.msh"
            mesh_file = jig_work_dir / "mesh.msh"

            # STL → JIGSAW msh 형식으로 변환 (meshio 사용)
            import meshio as _meshio

            surf_mesh = _meshio.read(str(preprocessed_path))
            _meshio.write(str(geom_file), surf_mesh, file_format="medit")

            # JIGSAW 옵션 설정
            opts = jigsawpy.jigsaw_jig_t()

            opts.geom_file = str(geom_file)
            opts.mesh_file = str(mesh_file)

            opts.hfun_hmax = hmax
            opts.hfun_hmin = hmin
            opts.hfun_scal = "relative"

            opts.mesh_dims = +3       # 3D
            opts.mesh_top1 = True     # 1-복잡체 위상 복원
            opts.geom_feat = True     # 특징 감지

            opts.optm_iter = params.get("jigsaw_optm_iter", 32)
            opts.verbosity = 0

            # JIGSAW 실행
            jigsawpy.cmd.jigsaw(opts)

            # 결과 읽기 (JIGSAW는 medit .msh 형식 출력)
            if not mesh_file.exists():
                raise RuntimeError(f"JIGSAW 결과 파일이 생성되지 않았습니다: {mesh_file}")

            result = _meshio.read(str(mesh_file))
            tetra_cells = [c for c in result.cells if c.type == "tetra"]

            if not tetra_cells:
                raise RuntimeError("JIGSAW 출력에 tet 셀이 없습니다.")

            tet_v = np.asarray(result.points, dtype=np.float64)
            tet_f = np.asarray(tetra_cells[0].data, dtype=np.int64)

            logger.info(
                "tier_jigsaw_mesh_built",
                num_points=len(tet_v),
                num_tets=len(tet_f),
            )

            # OpenFOAM polyMesh 변환
            writer = PolyMeshWriter()
            mesh_stats = writer.write(tet_v, tet_f, case_dir)

            # 작업 디렉터리 정리
            shutil.rmtree(str(jig_work_dir), ignore_errors=True)

            elapsed = time.monotonic() - t_start
            logger.info("tier_jigsaw_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_jigsaw_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"JIGSAW 실행 실패: {exc}",
            )
