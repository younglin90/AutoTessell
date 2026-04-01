"""Tier 0.5: Netgen/ngsolve 메쉬 생성기."""

from __future__ import annotations

import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger
from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier05_netgen"

# CAD 파일 확장자 (패스스루 지원)
_CAD_EXTENSIONS = {".step", ".stp", ".iges", ".igs", ".brep", ".brp"}


class Tier05NetgenGenerator:
    """Netgen/ngsolve 기반 테트라헤드럴 메쉬 생성기.

    STEP/IGES CAD 파일을 직접 읽어 고품질 tet 메쉬를 생성한다.
    STL 입력 시 STLGeometry를 사용한다.
    결과는 Gmsh2 포맷으로 export 후 gmshToFoam으로 변환한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 0.5 메쉬 생성을 실행한다.

        Args:
            strategy: Strategist가 생성한 메쉬 전략.
            preprocessed_path: 전처리된 STL 또는 CAD 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt. 실패 시 status="failed".
        """
        t_start = time.monotonic()
        logger.info("tier05_netgen_start", preprocessed_path=str(preprocessed_path))

        # netgen 모듈 import 시도
        try:
            import netgen.meshing as nm  # noqa: F401
            from netgen.stl import STLGeometry  # noqa: F401
            from netgen.occ import OCCGeometry  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier05_netgen_import_failed",
                error=str(exc),
                hint="netgen/ngsolve 미설치. 'pip install netgen-mesher' 또는 패키지 매니저 사용.",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    f"netgen 모듈 import 실패: {exc}. "
                    "'pip install netgen-mesher' 또는 시스템 패키지 설치 필요."
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

        # 메쉬 생성 실행
        try:
            params = strategy.tier_specific_params
            maxh = strategy.surface_mesh.target_cell_size
            minh = strategy.surface_mesh.min_cell_size
            grading = params.get("netgen_grading", 0.3)
            curvaturesafety = params.get("netgen_curvaturesafety", 2.0)
            segmentsperedge = params.get("netgen_segmentsperedge", 1.0)

            is_cad = preprocessed_path.suffix.lower() in _CAD_EXTENSIONS

            logger.info(
                "tier05_netgen_meshing",
                is_cad=is_cad,
                maxh=maxh,
                minh=minh,
                grading=grading,
            )

            if is_cad:
                geo = OCCGeometry(str(preprocessed_path))
            else:
                geo = STLGeometry(str(preprocessed_path))

            mesh = geo.GenerateMesh(
                maxh=maxh,
                minh=minh,
                grading=grading,
                curvaturesafety=curvaturesafety,
                segmentsperedge=segmentsperedge,
            )

            # Gmsh2 포맷으로 export
            msh_path = case_dir / "netgen_mesh.msh"
            mesh.Export(str(msh_path), "Gmsh2 Format")

            logger.info("tier05_netgen_msh_exported", path=str(msh_path))

            # gmshToFoam으로 polyMesh 변환 (OpenFOAM 미설치 시 PolyMeshWriter fallback)
            try:
                run_openfoam("gmshToFoam", case_dir, args=[str(msh_path)])
                logger.info("tier05_netgen_gmshtfoam_done")
            except (OpenFOAMError, FileNotFoundError) as gmsh_exc:
                logger.info(
                    "tier05_netgen_gmshtfoam_unavailable",
                    reason=str(gmsh_exc),
                    fallback="PolyMeshWriter",
                )
                import meshio as _meshio
                msh_data = _meshio.read(str(msh_path))
                tets = None
                for cb in msh_data.cells:
                    if cb.type == "tetra":
                        tets = cb.data
                        break
                if tets is None:
                    raise RuntimeError("No tetra cells found in Netgen mesh export")
                from core.generator.polymesh_writer import PolyMeshWriter
                writer = PolyMeshWriter()
                writer.write(msh_data.points, tets, case_dir)
                logger.info("tier05_netgen_polymesh_writer_done")

            elapsed = time.monotonic() - t_start
            logger.info("tier05_netgen_success", elapsed=elapsed)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier05_netgen_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 0.5 실행 실패: {exc}",
            )
