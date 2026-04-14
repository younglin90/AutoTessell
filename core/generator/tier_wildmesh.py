"""Tier WildMesh: wildmeshing (fTetWild Python 바인딩) 기반 Tet 메쉬 생성기."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_wildmesh"

# wildmeshing import 가용 여부
try:
    import wildmeshing  # noqa: F401
    _HAS_WILDMESHING = True
except ImportError:
    _HAS_WILDMESHING = False


def _get_quality_params(quality_level: str, params: dict[str, Any]) -> tuple[float, int, float | None]:
    """quality_level에 따른 기본 파라미터를 반환하고 tier_specific_params로 오버라이드한다.

    Args:
        quality_level: "draft" | "standard" | "fine"
        params: strategy.tier_specific_params

    Returns:
        (stop_quality, max_its, epsilon) 튜플. epsilon은 None이면 미사용.
    """
    if quality_level == "draft":
        default_stop_quality = 20.0
        default_max_its = 40
    elif quality_level == "fine":
        default_stop_quality = 5.0
        default_max_its = 200
    else:  # standard
        default_stop_quality = 10.0
        default_max_its = 80

    stop_quality = float(params.get("wildmesh_stop_quality", default_stop_quality))
    max_its = int(params.get("wildmesh_max_its", default_max_its))
    epsilon: float | None = params.get("wildmesh_epsilon", None)
    if epsilon is not None:
        epsilon = float(epsilon)

    return stop_quality, max_its, epsilon


class TierWildMeshGenerator:
    """wildmeshing (fTetWild) 기반 테트라헤드럴 메쉬 생성기.

    wildmeshing 라이브러리가 없으면 즉시 failed를 반환한다.
    External flow는 tier2_tetwild.py와 동일하게 trimesh domain box + body 복합 표면으로 처리한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """wildmeshing Tetrahedralizer 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier_wildmesh_start", preprocessed_path=str(preprocessed_path))

        # wildmeshing 가용 여부 확인
        if not _HAS_WILDMESHING:
            elapsed = time.monotonic() - t_start
            msg = (
                "wildmeshing 미설치. "
                "설치: pip install wildmeshing (또는 conda install -c conda-forge wildmeshing)"
            )
            logger.warning("tier_wildmesh_import_failed", hint=msg)
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=msg,
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
            import numpy as np
            import trimesh as _trimesh
            import wildmeshing as wm

            params = strategy.tier_specific_params
            quality_level = getattr(strategy, "quality_level", "standard")
            if hasattr(quality_level, "value"):
                quality_level = quality_level.value

            stop_quality, max_its, epsilon = _get_quality_params(quality_level, params)

            logger.info(
                "tier_wildmesh_params",
                stop_quality=stop_quality,
                max_its=max_its,
                epsilon=epsilon,
                quality_level=quality_level,
            )

            # 표면 로드
            surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]

            # TetWild 진입 전 열린 표면 닫기 시도
            if not surf.is_watertight:
                logger.info("wildmesh_pre_close_open_surface", method="trimesh_fill_holes")
                surf.fill_holes()
                if not surf.is_watertight:
                    try:
                        import pymeshfix
                        mf = pymeshfix.MeshFix(surf.vertices, surf.faces)
                        mf.repair()
                        surf = _trimesh.Trimesh(vertices=mf.points, faces=mf.faces)
                        logger.info("wildmesh_pre_close_pymeshfix_success")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("wildmesh_pre_close_pymeshfix_failed", error=str(e))
                if not surf.is_watertight:
                    logger.warning("wildmesh_surface_still_open_proceeding")

            # External flow: 도메인 박스 + 물체 복합 지오메트리 구성
            # External flow에서는 도메인 박스(뒤집힌 법선) + 물체 표면을 결합해
            # wildmeshing이 도메인 - 물체 영역을 메싱하도록 한다.
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
                domain_box.invert()  # 법선을 안쪽으로 → 도메인 경계 표시
                compound = _trimesh.util.concatenate([surf, domain_box])
                vertices = np.asarray(compound.vertices, dtype=np.float64)
                faces = np.asarray(compound.faces, dtype=np.int32)
                logger.info(
                    "wildmesh_external_flow_compound",
                    body_faces=len(surf.faces),
                    domain_faces=len(domain_box.faces),
                )
            else:
                vertices = np.asarray(surf.vertices, dtype=np.float64)
                faces = np.asarray(surf.faces, dtype=np.int32)

            # Tetrahedralizer 생성 및 실행
            tetra_kwargs: dict[str, Any] = {
                "stop_quality": stop_quality,
                "max_its": max_its,
            }
            if epsilon is not None:
                tetra_kwargs["epsilon"] = epsilon

            logger.info("wildmesh_tetrahedralize_start", **tetra_kwargs)
            tetra = wm.Tetrahedralizer(**tetra_kwargs)
            tetra.set_mesh(vertices, faces)
            tetra.tetrahedralize()
            tet_v, tet_f = tetra.get_tet_mesh()

            logger.info(
                "wildmesh_tetrahedralize_done",
                num_vertices=len(tet_v),
                num_tets=len(tet_f),
            )

            if len(tet_v) == 0 or len(tet_f) == 0:
                raise RuntimeError("wildmeshing이 빈 메쉬를 반환했습니다.")

            # PolyMeshWriter로 polyMesh 변환
            logger.info("wildmesh_polymesh_write_start", case_dir=str(case_dir))
            writer = PolyMeshWriter()
            mesh_stats = writer.write(tet_v, tet_f, case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier_wildmesh_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_wildmesh_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"tier_wildmesh 실행 실패: {exc}",
            )
