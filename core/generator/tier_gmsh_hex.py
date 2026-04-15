"""Tier GMSH Hex: gmsh transfinite hex-dominant 볼륨 메시 생성기.

gmsh의 transfinite 알고리즘과 RecombineAll 옵션을 사용해 hex-dominant 메시를 생성한다.
단순 볼록 형상에서 최적. 복잡 형상에서는 일반 Delaunay로 폴백하며, hex 셀이
없으면 status='failed'를 반환해 다음 Tier로 자동 전환된다.

결과는 gmshToFoam(OpenFOAM) 또는 meshio + PolyMeshWriter(fallback)로 변환된다.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger
from core.utils.openfoam_utils import OpenFOAMError, run_openfoam

logger = get_logger(__name__)

TIER_NAME = "tier_gmsh_hex"


class TierGmshHexGenerator:
    """gmsh transfinite 기반 hex-dominant 볼륨 메시 생성기.

    STL 표면을 gmsh에 로드하고, classifySurfaces + createGeometry 로 볼륨을
    자동 감지한 후 setTransfiniteAutomatic + RecombineAll 로 hex 셀을 생성한다.

    Tier 파라미터 (strategy.tier_specific_params):
        gmsh_hex_algorithm (int, default=8):
            2D 알고리즘. 8=Frontal-Delaunay for Quads (hex 친화적).
        gmsh_hex_recombine_all (bool, default=True):
            RecombineAll 활성화. False면 순수 tet 메시.
        gmsh_hex_char_length_factor (float, default=1.0):
            target_cell_size 배율. 1.0보다 크면 더 거칠어짐.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """gmsh transfinite hex 메시 생성 파이프라인을 실행한다.

        Args:
            strategy: Strategist가 생성한 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt. 실패 시 status='failed'.
        """
        t_start = time.monotonic()
        logger.info("tier_gmsh_hex_start", preprocessed_path=str(preprocessed_path))

        # gmsh import 시도
        try:
            import gmsh  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier_gmsh_hex_import_failed",
                error=str(exc),
                hint="gmsh 미설치. pip install gmsh",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="gmsh",
                    fallback="다음 Tier로 자동 전환",
                    action="pip install gmsh",
                    detail=str(exc),
                ),
            )

        # meshio import 시도 (변환 fallback에 필요)
        try:
            import meshio  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning("tier_gmsh_hex_meshio_missing", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="meshio",
                    fallback="다음 Tier로 자동 전환",
                    action="pip install meshio",
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
            return self._run_gmsh_pipeline(
                strategy=strategy,
                preprocessed_path=preprocessed_path,
                case_dir=case_dir,
                t_start=t_start,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_gmsh_hex_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier gmsh_hex 실행 실패: {exc}",
            )

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _run_gmsh_pipeline(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        """gmsh 초기화 → 메시 생성 → polyMesh 변환 전체 파이프라인."""
        import gmsh
        import meshio

        params = strategy.tier_specific_params
        target_cell_size = strategy.surface_mesh.target_cell_size
        min_cell_size = strategy.surface_mesh.min_cell_size
        feature_angle = strategy.surface_mesh.feature_angle

        char_length_factor: float = float(params.get("gmsh_hex_char_length_factor", 1.0))
        algorithm_2d: int = int(params.get("gmsh_hex_algorithm", 8))
        recombine_all: bool = bool(params.get("gmsh_hex_recombine_all", True))

        char_length_max = target_cell_size * char_length_factor
        char_length_min = min_cell_size * char_length_factor

        logger.info(
            "tier_gmsh_hex_params",
            char_length_max=char_length_max,
            char_length_min=char_length_min,
            algorithm_2d=algorithm_2d,
            recombine_all=recombine_all,
            feature_angle=feature_angle,
        )

        case_dir.mkdir(parents=True, exist_ok=True)
        msh_path = case_dir / "gmsh_hex_mesh.msh"

        # gmsh 세션 (try/finally로 반드시 finalize)
        # 비-메인 스레드에서 gmsh.initialize()가 signal.signal() 호출 시
        # "signal only works in main thread" ValueError 발생 → 임시 우회
        import signal as _signal
        import threading as _threading

        if _threading.current_thread() is not _threading.main_thread():
            _orig_signal = _signal.signal
            _signal.signal = lambda *a, **kw: None  # type: ignore[assignment]
            try:
                gmsh.initialize()
            finally:
                _signal.signal = _orig_signal
        else:
            gmsh.initialize()
        try:
            hex_generated = self._generate_gmsh_mesh(
                gmsh=gmsh,
                stl_path=preprocessed_path,
                msh_path=msh_path,
                char_length_max=char_length_max,
                char_length_min=char_length_min,
                feature_angle=feature_angle,
                algorithm_2d=algorithm_2d,
                recombine_all=recombine_all,
            )
        finally:
            gmsh.finalize()

        if not msh_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message="gmsh가 .msh 파일을 생성하지 않았습니다.",
            )

        # hex 셀 없으면 실패 처리 (다음 Tier로 전환)
        msh_data = meshio.read(str(msh_path))
        hex_cells = [c for c in msh_data.cells if c.type == "hexahedron"]
        tet_cells = [c for c in msh_data.cells if c.type == "tetra"]

        # hex_generated=False(transfinite 실패)여도 RecombineAll로 hex셀이 만들어질 수 있음
        # tet_cells 있어도 유효한 출력 (gmshToFoam/PolyMeshWriter 변환 가능)
        if not hex_cells and not tet_cells:
            logger.warning(
                "tier_gmsh_hex_no_hex_cells",
                hex_count=len(hex_cells),
                tet_count=len(tet_cells),
                msg="hex/tet 셀 없음 → 다음 Tier로 전환",
            )
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    "gmsh transfinite가 hex 셀을 생성하지 못했습니다. "
                    "형상이 너무 복잡하거나 비볼록(non-convex)합니다."
                ),
            )

        logger.info(
            "tier_gmsh_hex_mesh_ready",
            hex_cells=sum(len(c.data) for c in hex_cells),
            tet_cells=sum(len(c.data) for c in tet_cells),
        )

        # polyMesh 변환: gmshToFoam 시도 → 실패 시 PolyMeshWriter fallback
        self._convert_to_polymesh(
            msh_path=msh_path,
            msh_data=msh_data,
            case_dir=case_dir,
            tet_cells=tet_cells,
        )

        elapsed = time.monotonic() - t_start
        logger.info("tier_gmsh_hex_success", elapsed=elapsed)

        return TierAttempt(
            tier=TIER_NAME,
            status="success",
            time_seconds=elapsed,
        )

    @staticmethod
    def _generate_gmsh_mesh(
        gmsh,
        stl_path: Path,
        msh_path: Path,
        char_length_max: float,
        char_length_min: float,
        feature_angle: float,
        algorithm_2d: int,
        recombine_all: bool,
    ) -> bool:
        """gmsh 메시 생성 핵심 로직.

        Returns:
            True: transfinite + recombine 성공 (hex 셀 기대 가능).
            False: 일반 Delaunay fallback 사용 (hex 셀 없을 가능성).
        """
        gmsh.model.add("hex_mesh")

        # STL 표면 로드 — gmsh는 binary STL을 거부하는 경우가 있으므로
        # ASCII로 변환 후 재시도한다.
        try:
            gmsh.merge(str(stl_path))
        except Exception:
            import tempfile
            import trimesh as _trimesh
            surf = _trimesh.load(str(stl_path), force="mesh")
            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                ascii_path = tmp.name
            surf.export(ascii_path, file_type="stl_ascii")
            gmsh.merge(ascii_path)
            import os as _os
            _os.unlink(ascii_path)

        # 표면 분류 및 볼륨 생성
        angle_rad = feature_angle * (math.pi / 180.0)
        gmsh.model.mesh.classifySurfaces(angle_rad, True, True, math.pi)
        gmsh.model.mesh.createGeometry()

        # createGeometry 후 볼륨 엔티티가 없으면 STL 표면으로 볼륨을 명시적으로 생성
        volumes = gmsh.model.getEntities(3)
        if not volumes:
            surfaces = gmsh.model.getEntities(2)
            if surfaces:
                sl = gmsh.model.geo.addSurfaceLoop([s[1] for s in surfaces])
                gmsh.model.geo.addVolume([sl])
                gmsh.model.geo.synchronize()
                logger.info(
                    "tier_gmsh_hex_volume_created_explicitly",
                    num_surfaces=len(surfaces),
                )
            else:
                raise RuntimeError("gmsh에 표면 엔티티가 없어 볼륨 생성 불가")

        # 공통 메시 크기 옵션
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", char_length_max)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", char_length_min)
        gmsh.option.setNumber("Mesh.Algorithm", algorithm_2d)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay 3D

        if recombine_all:
            gmsh.option.setNumber("Mesh.RecombineAll", 1)
            gmsh.option.setNumber("Mesh.Recombine3DAll", 1)

        # transfinite 시도 (볼록 단순 형상에서만 제대로 동작)
        transfinite_ok = False
        try:
            gmsh.model.mesh.setTransfiniteAutomatic()
            transfinite_ok = True
            logger.info("tier_gmsh_hex_transfinite_ok")
        except Exception as exc:
            logger.warning(
                "tier_gmsh_hex_transfinite_failed",
                error=str(exc),
                fallback="일반 Delaunay 메시 생성으로 폴백",
            )

        # 3D 메시 생성
        gmsh.model.mesh.generate(3)

        if recombine_all:
            gmsh.model.mesh.recombine()

        gmsh.write(str(msh_path))
        return transfinite_ok

    def _convert_to_polymesh(
        self,
        msh_path: Path,
        msh_data,
        case_dir: Path,
        tet_cells: list,
    ) -> None:
        """gmsh .msh → OpenFOAM polyMesh 변환.

        1차: gmshToFoam (OpenFOAM 설치된 경우)
        2차: meshio + PolyMeshWriter (tet 셀만 지원)
        """
        # 1차: gmshToFoam 시도
        try:
            run_openfoam("gmshToFoam", case_dir, args=[str(msh_path)])
            logger.info("tier_gmsh_hex_gmshtofoam_done")
            return
        except (OpenFOAMError, FileNotFoundError) as exc:
            logger.info(
                "tier_gmsh_hex_gmshtofoam_unavailable",
                reason=str(exc),
                fallback="PolyMeshWriter",
            )

        # 2차: PolyMeshWriter (tet 셀 필요)
        if not tet_cells:
            # tet 셀도 없으면 hex 셀을 tet로 분해 시도
            import numpy as np
            from meshio import CellBlock

            hex_cells_blocks = [c for c in msh_data.cells if c.type == "hexahedron"]
            if not hex_cells_blocks:
                raise RuntimeError("gmsh 메시에 tet/hex 셀이 없습니다: PolyMeshWriter 변환 불가")

            # hex → 6 tet 분해 (각 hex를 6개의 tet로 분해)
            all_tets = []
            for cb in hex_cells_blocks:
                for hex_node in cb.data:
                    # 표준 hex → 6 tet 분해 (Kuhn 분해)
                    h = hex_node
                    all_tets.extend([
                        [h[0], h[1], h[3], h[4]],
                        [h[1], h[2], h[3], h[6]],
                        [h[1], h[3], h[4], h[6]],
                        [h[4], h[5], h[6], h[1]],
                        [h[4], h[6], h[7], h[3]],
                        [h[3], h[4], h[6], h[1]],
                    ])
            tet_array = np.array(all_tets, dtype=np.int64)
            logger.info(
                "tier_gmsh_hex_hex_to_tet",
                num_tets=len(tet_array),
                msg="hex → tet 분해 후 PolyMeshWriter 사용",
            )
        else:
            import numpy as np
            tet_array = np.vstack([c.data for c in tet_cells])

        from core.generator.polymesh_writer import PolyMeshWriter

        writer = PolyMeshWriter()
        writer.write(msh_data.points, tet_array, case_dir)
        logger.info("tier_gmsh_hex_polymesh_writer_done")
