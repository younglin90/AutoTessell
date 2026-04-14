"""Tier JIGSAW: 강건한 비구조 Tet 메싱 (TetWild fallback).

TetWild 실패 시 자동 전환. JIGSAW는 보수적이지만 극도로 안정적이다.
Draft 품질 경로에서 최후의 fallback으로 사용된다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_jigsaw_fallback"


class TierJigsawFallbackGenerator:
    """JIGSAW 기반 강건한 Tet 메시 생성기.

    TetWild가 실패한 경우의 최후 fallback. 성능은 다소 떨어지지만
    매우 높은 성공률과 좋은 메시 품질을 제공한다.
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
        logger.info("tier_jigsaw_fallback_start", preprocessed_path=str(preprocessed_path))

        # jigsawpy import 시도
        try:
            import jigsawpy  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_jigsaw_fallback_import_failed",
                error=str(exc),
                hint="jigsawpy 미설치. pip install jigsawpy",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="jigsawpy",
                    fallback="모든 Tier 실패",
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
            import jigsawpy as jigsaw
            import trimesh as _trimesh

            # STL 로드
            surf: _trimesh.Trimesh = _trimesh.load(
                str(preprocessed_path), force="mesh"
            )  # type: ignore[assignment]

            # 파라미터 설정
            params = strategy.tier_specific_params

            # External flow: 도메인 박스 + 물체 복합 지오메트리 구성
            # JIGSAW는 닫힌 표면의 내부를 메싱한다.
            # External flow에서는 "도메인 박스 내부 - 물체 내부" 영역이 유동 도메인이므로
            # 도메인 박스를 뒤집은 법선(안쪽)으로 추가하여 JIGSAW에 전달한다.
            flow_type = getattr(strategy, "flow_type", "internal")
            if flow_type == "external" and strategy.domain is not None:
                domain = strategy.domain
                box_size = [
                    float(domain.max[0] - domain.min[0]),
                    float(domain.max[1] - domain.min[1]),
                    float(domain.max[2] - domain.min[2]),
                ]
                box_center = [
                    float((domain.min[0] + domain.max[0]) / 2),
                    float((domain.min[1] + domain.max[1]) / 2),
                    float((domain.min[2] + domain.max[2]) / 2),
                ]
                domain_box = _trimesh.creation.box(extents=box_size)
                domain_box.apply_translation(box_center)
                # 도메인 박스 법선을 안쪽으로 뒤집어 JIGSAW에게 "외부 경계"임을 알림
                domain_box.invert()

                # 복합 표면: 물체 표면 + 뒤집힌 도메인 박스
                compound = _trimesh.util.concatenate([surf, domain_box])
                vertices = compound.vertices
                faces = compound.faces
                logger.info(
                    "jigsaw_external_flow_compound",
                    body_faces=len(surf.faces),
                    domain_faces=len(domain_box.faces),
                    total_faces=len(faces),
                )
            else:
                # Internal flow: 물체 내부를 유동 도메인으로 직접 메싱
                vertices = surf.vertices
                faces = surf.faces
            quality_level = getattr(strategy, "quality_level", "standard")
            if hasattr(quality_level, "value"):
                quality_level = quality_level.value

            # JIGSAW 파라미터 (quality level에 따라 조정)
            if quality_level == "draft":
                hmax = params.get("jigsaw_hmax", strategy.surface_mesh.target_cell_size * 2.0)
                hmin = params.get("jigsaw_hmin", strategy.surface_mesh.target_cell_size * 0.5)
                quality = 95  # 속도 우선
            else:
                hmax = params.get("jigsaw_hmax", strategy.surface_mesh.target_cell_size)
                hmin = params.get("jigsaw_hmin", strategy.surface_mesh.target_cell_size * 0.1)
                quality = 100  # 품질 우선

            logger.info(
                "tier_jigsaw_fallback_meshing",
                hmax=hmax,
                hmin=hmin,
                quality=quality,
            )

            # JIGSAW 옵션 설정
            opts = jigsaw.jigsaw_msh()
            opts.geom_seed = 42  # 재현성
            opts.geom_feat = True  # 피처 보존
            opts.mesh_dims = 3  # 3D 메싱
            opts.hmax_grad = 1.25  # 크기 구배 제한
            opts.hmax = float(hmax)
            opts.hmin = float(hmin)
            opts.optm_qlim = quality / 100.0  # 품질 기준 (0~1)
            opts.mesh_top = True  # 위상 검증
            opts.mesh_sj = True  # Sliver 제거

            # 입력 메시 구성
            mesh = jigsaw.jigsaw_msh()
            mesh.vert3 = np.column_stack(
                [vertices, np.ones(len(vertices))]
            )  # (N, 4) with tag
            mesh.tria3 = np.column_stack(
                [faces, np.ones(len(faces), dtype=int)]
            )  # (M, 4) with tag

            # JIGSAW 메싱 실행
            logger.info("jigsaw_meshing_running")
            jigsaw.jigsaw(opts, mesh)

            # 결과 추출
            tet_v = mesh.vert3[:, :3]  # (N, 3) coordinates only
            tet_f = mesh.tetr4[:, :4]  # (M, 4) tet connectivity only

            if len(tet_v) == 0 or len(tet_f) == 0:
                raise RuntimeError("JIGSAW가 빈 메쉬를 반환했습니다.")

            logger.info(
                "jigsaw_mesh_built",
                num_points=len(tet_v),
                num_tets=len(tet_f),
            )

            # OpenFOAM polyMesh 변환
            writer = PolyMeshWriter()
            mesh_stats = writer.write(tet_v, tet_f, case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier_jigsaw_fallback_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_jigsaw_fallback_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier JIGSAW Fallback 실행 실패: {exc}",
            )
