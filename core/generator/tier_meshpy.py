"""Tier MeshPy: TetGen 기반 테트라헤드럴 메쉬 생성기.

Standard 품질 레벨에서 Netgen 실패 시 fallback으로 사용한다.
meshpy.tet (TetGen Python 바인딩)을 사용하여 tet 메쉬를 생성한다.
"""

from __future__ import annotations

import time
from pathlib import Path

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_meshpy"


class TierMeshPyGenerator:
    """MeshPy TetGen 기반 테트라헤드럴 메쉬 생성기.

    Standard 품질 레벨에서 Netgen 실패 시 fallback으로 사용한다.
    meshpy.tet.build()로 고품질 구속 Delaunay 테트라헤드라이제이션을 수행한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """MeshPy TetGen 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier_meshpy_start", preprocessed_path=str(preprocessed_path))

        # meshpy import 시도
        try:
            import meshpy.tet as _mtet  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_meshpy_import_failed",
                error=str(exc),
                hint="meshpy 미설치. pip install meshpy",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="meshpy",
                    fallback="cfMesh/TetWild fallback",
                    action="pip install meshpy",
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
            import meshpy.tet as mtet
            import numpy as np
            import trimesh as _trimesh

            params = strategy.tier_specific_params
            max_vol = params.get(
                "meshpy_max_volume",
                strategy.surface_mesh.target_cell_size ** 3 / 6.0,
            )
            min_angle = params.get("meshpy_min_angle", 25.0)

            logger.info(
                "tier_meshpy_meshing",
                max_volume=max_vol,
                min_angle=min_angle,
            )

            # STL 로드
            surf: _trimesh.Trimesh = _trimesh.load(
                str(preprocessed_path), force="mesh"
            )  # type: ignore[assignment]
            vertices = surf.vertices
            faces = surf.faces

            # MeshPy MeshInfo 구성
            mesh_info = mtet.MeshInfo()
            mesh_info.set_points(vertices.tolist())
            mesh_info.set_facets(faces.tolist())

            # TetGen 옵션: 구속 Delaunay, 품질 개선
            # 'p' = PLCmesh, 'q{angle}' = quality, 'a{vol}' = max volume constraint
            switch_str = f"pq{min_angle:.1f}a{max_vol:.10e}"
            opts = mtet.Options(switch_str)

            result_mesh = mtet.build(mesh_info, opts)

            tet_v = np.array(result_mesh.points, dtype=np.float64)
            tet_f = np.array(result_mesh.elements, dtype=np.int64)

            if len(tet_v) == 0 or len(tet_f) == 0:
                raise RuntimeError("MeshPy TetGen이 빈 메쉬를 반환했습니다.")

            logger.info(
                "tier_meshpy_mesh_built",
                num_points=len(tet_v),
                num_tets=len(tet_f),
            )

            # OpenFOAM polyMesh 변환
            writer = PolyMeshWriter()
            mesh_stats = writer.write(tet_v, tet_f, case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier_meshpy_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_meshpy_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"MeshPy TetGen 실행 실패: {exc}",
            )
