"""Tier JIGSAW: 비구조 tet 메쉬 생성기.

Draft 품질 레벨에서 TetWild 실패 시 fallback으로 사용한다.
jigsawpy libsaw ctypes API로 3D 비구조 tet 메쉬를 생성한다.
바이너리 불필요 — libjigsaw.so (jigsawpy/_lib/)만 있으면 작동.
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
    """JIGSAW libsaw ctypes 기반 비구조 tet 메쉬 생성기.

    jigsawpy._lib/libjigsaw.so를 ctypes로 직접 호출.
    별도 바이너리 불필요.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_jigsaw_start", preprocessed_path=str(preprocessed_path))

        # jigsawpy + libjigsaw.so 로드 확인
        try:
            from jigsawpy.libsaw import jigsaw as _libsaw_jigsaw  # noqa: F401
        except (ImportError, ValueError, OSError) as exc:
            elapsed = time.monotonic() - t_start
            logger.warning("tier_jigsaw_import_failed", error=str(exc),
                           hint="jigsawpy/_lib/libjigsaw.so 가 필요합니다.")
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="jigsawpy+libjigsaw.so",
                    fallback="다른 tier로 fallback",
                    action="jigsawpy/_lib/libjigsaw.so 설치 필요",
                    detail=str(exc),
                ),
            )

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_jigsaw(strategy, preprocessed_path, case_dir, t_start)
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_jigsaw_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"JIGSAW 실행 실패: {exc}",
            )

    def _run_jigsaw(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import numpy as np
        import trimesh
        from jigsawpy import jigsaw_jig_t, jigsaw_msh_t
        from jigsawpy.libsaw import jigsaw as libsaw_jigsaw

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        # jigsaw_hmax_scale: draft coarse 모드(기존 fallback 동작)는 2.0, 기본 1.0
        hmax_scale = float(params.get("jigsaw_hmax_scale", 1.0))
        hmax = float(params.get("jigsaw_hmax", strategy.surface_mesh.target_cell_size * hmax_scale))
        hmin = float(params.get("jigsaw_hmin", strategy.surface_mesh.min_cell_size))
        optm_iter = int(params.get("jigsaw_optm_iter", 32))

        logger.info("tier_jigsaw_meshing", hmax=hmax, hmin=hmin, optm_iter=optm_iter)

        # STL → trimesh 로드
        surf = trimesh.load(str(preprocessed_path), force="mesh")
        verts = np.array(surf.vertices, dtype=float)
        faces = np.array(surf.faces, dtype=np.int32)

        # geometry jigsaw_msh_t 빌드
        geom = jigsaw_msh_t()
        geom.mshID = "euclidean-mesh"
        geom.ndims = 3

        geom.vert3 = np.empty(len(verts), dtype=geom.VERT3_t)
        geom.vert3["coord"][:, 0] = verts[:, 0]
        geom.vert3["coord"][:, 1] = verts[:, 1]
        geom.vert3["coord"][:, 2] = verts[:, 2]
        geom.vert3["IDtag"] = 0

        geom.tria3 = np.empty(len(faces), dtype=geom.TRIA3_t)
        geom.tria3["index"][:, 0] = faces[:, 0]
        geom.tria3["index"][:, 1] = faces[:, 1]
        geom.tria3["index"][:, 2] = faces[:, 2]
        geom.tria3["IDtag"] = 0

        # 출력 mesh
        mesh = jigsaw_msh_t()

        # 옵션
        opts = jigsaw_jig_t()
        opts.hfun_hmax = hmax
        opts.hfun_hmin = hmin
        opts.mesh_dims = 3
        opts.geom_feat = True
        opts.mesh_top1 = True
        opts.optm_iter = optm_iter
        opts.verbosity = 0

        # libsaw ctypes 직접 호출 (바이너리 불필요)
        libsaw_jigsaw(opts, geom, mesh)

        # tet 셀 확인
        if mesh.tria4 is None or len(mesh.tria4) == 0:
            raise RuntimeError(
                f"JIGSAW 출력에 tet 셀이 없습니다. "
                f"vert3={len(mesh.vert3) if mesh.vert3 is not None else 0}"
            )

        tet_v = np.asarray(mesh.vert3["coord"], dtype=np.float64)
        tet_f = np.asarray(mesh.tria4["index"][:, :4], dtype=np.int64)

        logger.info("tier_jigsaw_mesh_built", num_points=len(tet_v), num_tets=len(tet_f))

        # OpenFOAM polyMesh 변환
        writer = PolyMeshWriter()
        mesh_stats = writer.write(tet_v, tet_f, case_dir)

        elapsed = time.monotonic() - t_start
        logger.info("tier_jigsaw_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
