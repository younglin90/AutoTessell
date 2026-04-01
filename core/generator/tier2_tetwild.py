"""Tier 2: TetWild + MMG 메쉬 생성기 (최후 fallback)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from typing import Any

import numpy as np
import numpy.typing as npt

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier2_tetwild"


def _try_gmsh_to_foam(mesh_path: Path, case_dir: Path) -> bool:
    """gmshToFoam が使える場合に実行する。

    Args:
        mesh_path: .msh ファイルパス.
        case_dir: OpenFOAM ケースディレクトリ.

    Returns:
        True if gmshToFoam succeeded, False otherwise.
    """
    gmsh_to_foam = shutil.which("gmshToFoam")
    if gmsh_to_foam is None:
        logger.debug("gmshToFoam_not_found", hint="OpenFOAM not installed, using PolyMeshWriter")
        return False

    try:
        from core.utils.openfoam_utils import run_openfoam
        run_openfoam("gmshToFoam", case_dir, args=[str(mesh_path)])
        logger.info("gmsh_to_foam_success", mesh_path=str(mesh_path))
        return True
    except Exception as exc:
        logger.warning("gmsh_to_foam_failed", error=str(exc))
        return False


def _convert_to_openfoam(vertices: npt.NDArray[Any], tets: npt.NDArray[Any], mesh_path: Path, case_dir: Path) -> dict[str, int]:
    """tet 메쉬를 OpenFOAM polyMesh로 변환한다.

    먼저 gmshToFoam (OpenFOAM 설치 시)을 시도하고, 없으면 PolyMeshWriter를 사용한다.

    Args:
        vertices: (N, 3) float array.
        tets: (M, 4) int array.
        mesh_path: meshio로 저장한 .msh 파일 경로.
        case_dir: OpenFOAM 케이스 디렉터리 경로.

    Returns:
        dict with mesh stats from PolyMeshWriter (or empty dict if gmshToFoam used).
    """
    # Try gmshToFoam first (requires OpenFOAM)
    if _try_gmsh_to_foam(mesh_path, case_dir):
        return {}

    # Fall back to standalone PolyMeshWriter
    logger.info("polymesh_writer_convert", src=str(mesh_path), dst=str(case_dir))
    writer = PolyMeshWriter()
    return writer.write(vertices, tets, case_dir)


class Tier2TetWildGenerator:
    """TetWild + MMG 기반 테트라헤드럴 메쉬 생성기.

    최후 fallback Tier. 극단적으로 불량한 지오메트리도 처리 가능한
    강건한 알고리즘을 사용한다.
    MMG가 설치된 경우 메쉬 품질 후처리를 수행한다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Tier 2 TetWild + MMG 파이프라인을 실행한다.

        Args:
            strategy: 메쉬 전략.
            preprocessed_path: 전처리된 STL 파일 경로.
            case_dir: OpenFOAM 케이스 디렉터리 경로.

        Returns:
            실행 결과를 담은 TierAttempt.
        """
        t_start = time.monotonic()
        logger.info("tier2_tetwild_start", preprocessed_path=str(preprocessed_path))

        # pytetwild 모듈 import 시도
        try:
            import pytetwild  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            logger.warning(
                "tier2_tetwild_import_failed",
                error=str(exc),
                hint="pytetwild 미설치. pip install pytetwild",
            )
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"pytetwild 모듈 import 실패: {exc}. pip install pytetwild",
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

            # quality_level에 따른 기본 파라미터 결정
            quality_level = getattr(strategy, "quality_level", "standard")
            if hasattr(quality_level, "value"):
                quality_level = quality_level.value

            if quality_level == "draft":
                default_epsilon = 0.02
                default_stop_energy = 20.0
            else:
                default_epsilon = 1e-3
                default_stop_energy = 10.0

            epsilon = params.get("tetwild_epsilon", default_epsilon)
            edge_length = params.get("tetwild_edge_length", None)
            stop_energy = params.get("tetwild_stop_energy", default_stop_energy)

            logger.info(
                "tier2_tetwild_meshing",
                epsilon=epsilon,
                edge_length=edge_length,
                stop_energy=stop_energy,
            )

            import trimesh as _trimesh
            import pytetwild

            surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]
            vertices = surf.vertices
            faces = surf.faces

            tetra_kwargs: dict[str, Any] = {
                "stop_energy": stop_energy,
            }
            if edge_length is not None:
                tetra_kwargs["edge_len_r"] = edge_length

            tet_v, tet_f = pytetwild.tetrahedralize(vertices, faces, **tetra_kwargs)  # type: ignore[attr-defined]

            # meshio로 .msh 저장 (gmshToFoam 경로에서 사용)
            import meshio as _meshio
            tet_mesh = _meshio.Mesh(
                points=tet_v,
                cells=[("tetra", tet_f)],
            )
            result_msh = case_dir / "tetwild_result.msh"
            _meshio.write(str(result_msh), tet_mesh)
            logger.info("tetwild_msh_saved", path=str(result_msh))

            # MMG 품질 후처리 (standard/fine 전용 — draft는 속도 우선이므로 건너뜀)
            mmg_mesh_path = result_msh
            mmg_verts = tet_v
            mmg_tets = tet_f
            if quality_level in ("standard", "fine") and shutil.which("mmg3d"):
                mmg_mesh_path = self._run_mmg(result_msh, case_dir, params)
                # Re-read MMG output so we have updated arrays for PolyMeshWriter
                if mmg_mesh_path != result_msh:
                    try:
                        import meshio as _meshio2
                        mmg_result = _meshio2.read(str(mmg_mesh_path))
                        tetra_cells = [c for c in mmg_result.cells if c.type == "tetra"]
                        if tetra_cells:
                            mmg_verts = mmg_result.points
                            mmg_tets = tetra_cells[0].data
                    except Exception as mmg_read_exc:
                        logger.warning("mmg_read_failed", error=str(mmg_read_exc))

            # polyMesh 변환: gmshToFoam 또는 PolyMeshWriter
            mesh_stats = _convert_to_openfoam(mmg_verts, mmg_tets, mmg_mesh_path, case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier2_tetwild_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier2_tetwild_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier 2 실행 실패: {exc}",
            )

    def _convert_msh_to_medit(self, input_msh: Path, case_dir: Path) -> Path:
        """Gmsh .msh 파일을 MMG가 읽을 수 있는 Medit .mesh 형식으로 변환한다.

        Args:
            input_msh: Gmsh .msh 파일 경로.
            case_dir: 출력 디렉터리.

        Returns:
            변환된 .mesh 파일 경로. 실패 시 input_msh 반환.
        """
        medit_path = case_dir / "tetwild_result.mesh"
        try:
            import meshio as _meshio
            mesh = _meshio.read(str(input_msh))
            _meshio.write(str(medit_path), mesh, file_format="medit")
            logger.info("msh_to_medit_done", src=str(input_msh), dst=str(medit_path))
            return medit_path
        except Exception as exc:
            logger.warning("msh_to_medit_failed", error=str(exc), fallback=str(input_msh))
            return input_msh

    def _run_mmg(
        self,
        input_msh: Path,
        case_dir: Path,
        params: dict[str, Any],
    ) -> Path:
        """MMG3D를 사용해 메쉬 품질을 향상시킨다.

        MMG는 Medit (.mesh) 형식을 요구하므로 Gmsh .msh 파일은 먼저 변환한다.

        Args:
            input_msh: TetWild 결과 .msh 파일.
            case_dir: 케이스 디렉터리.
            params: tier_specific_params.

        Returns:
            최적화된 메쉬 파일 경로. 실패 시 input_msh 반환.
        """
        # hmin/hmax 기본값 계산 (strategy 없이도 동작)
        hmin = params.get("mmg_hmin", None)
        hmax = params.get("mmg_hmax", None)
        hgrad = params.get("mmg_hgrad", 1.3)
        hausd = params.get("mmg_hausd", 0.01)

        # MMG는 Medit .mesh 형식을 입력으로 요구 — .msh이면 변환
        if input_msh.suffix == ".msh":
            medit_input = self._convert_msh_to_medit(input_msh, case_dir)
        else:
            medit_input = input_msh

        optimized = case_dir / "mmg_optimized.mesh"

        cmd = ["mmg3d", str(medit_input)]
        if hmin is not None:
            cmd += ["-hmin", str(hmin)]
        if hmax is not None:
            cmd += ["-hmax", str(hmax)]
        cmd += ["-hgrad", str(hgrad), "-hausd", str(hausd), "-o", str(optimized)]

        logger.info("running_mmg3d", cmd=" ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode == 0 and optimized.exists():
                logger.info("mmg3d_success", output=str(optimized))
                return optimized
            else:
                logger.warning(
                    "mmg3d_failed",
                    returncode=result.returncode,
                    stderr=result.stderr[:300],
                )
                return input_msh
        except Exception as exc:
            logger.warning("mmg3d_exception", error=str(exc))
            return input_msh
