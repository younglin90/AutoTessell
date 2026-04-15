"""Tier MMG3D: MMG3D 기반 고품질 Tet 메쉬 생성기.

MMG3D (Mmg Platform) 바이너리를 사용해 고품질 적응형 tetrahedral 메쉬를 생성한다.

파이프라인:
  1. STL → Medit .mesh 변환 (meshio)
  2. tetgen/meshpy로 초기 tet 볼륨 메쉬 생성
  3. mmg3d로 메쉬 품질 최적화 (hausd/hmax/hmin 제어)
  4. polyMesh 변환 (PolyMeshWriter)

MMG3D는 다음 메트릭으로 메쉬 품질을 제어한다:
  - -hausd: Hausdorff 근사 오차 (표면 충실도)
  - -hmax/-hmin: 셀 크기 범위
  - -ar: 특징 각도 감지
  - -optim: 최적화 반복

참고:
  https://www.mmgtools.org/
  https://github.com/MmgTools/mmg
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_mmg3d"


def _find_mmg3d_binary() -> Path | None:
    """mmg3d 실행 파일 경로를 반환한다. 없으면 None.

    탐색 순서:
      1. 프로젝트 ``bin/`` 디렉터리 (인스톨러가 번들한 위치)
      2. PATH
      3. ``~/.local/bin`` (Linux)
      4. Windows 설치 경로
    """
    import sys

    project_bin = Path(__file__).resolve().parents[2] / "bin"

    # Windows: .exe 확장자 포함 탐색
    if sys.platform == "win32":
        win_names = ("mmg3d.exe", "mmg3d_O3.exe")
        for name in win_names:
            p = project_bin / name
            if p.exists():
                return p
        # 일반적인 Windows 설치 경로
        import os
        for win_dir in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "AutoTessell" / "bin",
            Path(r"C:\AutoTessell\bin"),
        ):
            for name in win_names:
                p = win_dir / name
                if p.exists():
                    return p

    # Linux/macOS: 프로젝트 bin/ 우선
    for name in ("mmg3d", "mmg3d_O3", "mmg3d_so"):
        p = project_bin / name
        if p.exists():
            return p
        found = shutil.which(name)
        if found:
            return Path(found)

    # ~/.local/bin (Linux)
    local_bin = Path.home() / ".local" / "bin" / "mmg3d"
    if local_bin.exists():
        return local_bin

    return None


class TierMMG3DGenerator:
    """MMG3D 기반 고품질 적응형 Tet 메쉬 생성기.

    Standard/Fine 품질 레벨에서 사용. 초기 tet 메쉬를 생성한 뒤
    mmg3d로 Hausdorff 근사 오차 기반 품질 최적화를 수행한다.

    Tier 파라미터 (strategy.tier_specific_params):
        mmg3d_hausd (float): Hausdorff 거리. 작을수록 표면 정확도↑.
        mmg3d_hmax (float): 최대 셀 크기.
        mmg3d_hmin (float): 최소 셀 크기.
        mmg3d_ar (float): 특징 각도 감지 (도). 기본 60.
        mmg3d_optim (bool): 추가 최적화 활성화.
        mmg3d_verbosity (int): mmg3d 출력 레벨. 기본 -1 (quiet).
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_mmg3d_start", preprocessed_path=str(preprocessed_path))

        # mmg3d 바이너리 확인
        mmg3d_bin = _find_mmg3d_binary()
        if mmg3d_bin is None:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    "mmg3d 바이너리를 찾을 수 없습니다. "
                    "https://www.mmgtools.org/ 에서 설치하거나 "
                    "'pip install mmg' (있을 경우) 또는 소스 빌드 후 PATH에 추가하세요."
                ),
            )

        # meshio import 확인
        try:
            import meshio  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"meshio 미설치: {exc}",
            )

        # meshpy import 확인 (초기 tet 메쉬 생성용)
        try:
            import meshpy.tet as mtet  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"meshpy 미설치 (초기 tet 생성 필요): {exc}. pip install meshpy",
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
            return self._run_mmg3d(
                mmg3d_bin=mmg3d_bin,
                strategy=strategy,
                preprocessed_path=preprocessed_path,
                case_dir=case_dir,
                t_start=t_start,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_mmg3d_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"MMG3D 실행 실패: {exc}",
            )

    def _run_mmg3d(
        self,
        mmg3d_bin: Path,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import meshio
        import meshpy.tet as mtet
        import trimesh

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value

        target_size = strategy.surface_mesh.target_cell_size
        min_size = strategy.surface_mesh.min_cell_size

        # draft 품질에서 너무 촘촘한 메쉬를 생성해 메모리 폭발을 방지한다.
        # hmax 기본값을 품질 레벨에 따라 차별화한다.
        if quality_level == "draft":
            default_hmax = target_size * 5.0   # 5배 coarser
            default_hausd = target_size * 0.5
        elif quality_level == "fine":
            default_hmax = target_size
            default_hausd = target_size * 0.05
        else:  # standard
            default_hmax = target_size * 2.0
            default_hausd = target_size * 0.1

        hausd: float = float(params.get("mmg3d_hausd", default_hausd))
        hmax: float = float(params.get("mmg3d_hmax", default_hmax))
        hmin: float = float(params.get("mmg3d_hmin", min_size))
        ar: float = float(params.get("mmg3d_ar", 60.0))
        do_optim: bool = bool(params.get("mmg3d_optim", True))
        verbosity: int = int(params.get("mmg3d_verbosity", -1))

        logger.info(
            "tier_mmg3d_params",
            hausd=hausd,
            hmax=hmax,
            hmin=hmin,
            ar=ar,
            optim=do_optim,
        )

        work_dir = case_dir / "_mmg3d_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # --- Step 1: STL → 초기 Tet 메쉬 (meshpy TetGen) ---
        surf = trimesh.load(str(preprocessed_path), force="mesh")
        verts = np.asarray(surf.vertices, dtype=np.float64)
        faces = np.asarray(surf.faces, dtype=np.int32)

        mesh_info = mtet.MeshInfo()
        mesh_info.set_points(verts.tolist())
        mesh_info.set_facets(faces.tolist())

        # TetGen 볼륨 제한: hmax 기반으로 계산해 메모리 폭발 방지
        max_vol = (hmax ** 3) / 6.0
        switch_str = f"pqa{max_vol:.10e}"
        logger.info("tier_mmg3d_tetgen_meshing", switch=switch_str, hmax=hmax, max_vol=max_vol)
        initial_mesh = mtet.build(mesh_info, options=mtet.Options(switch_str))

        tet_v = np.array(list(initial_mesh.points), dtype=np.float64)
        tet_f = np.array(list(initial_mesh.elements), dtype=np.int64)

        if len(tet_f) == 0:
            raise RuntimeError("TetGen 초기 메쉬 생성 실패: tet 셀 없음")

        logger.info(
            "tier_mmg3d_initial_mesh",
            num_points=len(tet_v),
            num_tets=len(tet_f),
        )

        # --- Step 2: 초기 메쉬 → Medit .mesh 저장 ---
        init_mesh_path = work_dir / "initial.mesh"
        init_meshio = meshio.Mesh(
            points=tet_v,
            cells=[("tetra", tet_f)],
        )
        meshio.write(str(init_mesh_path), init_meshio, file_format="medit")

        # --- Step 3: mmg3d 최적화 실행 ---
        opt_mesh_path = work_dir / "optimized.mesh"
        cmd = [
            str(mmg3d_bin),
            "-in", str(init_mesh_path),
            "-out", str(opt_mesh_path),
            "-hausd", str(hausd),
            "-hmax", str(hmax),
            "-hmin", str(hmin),
            "-ar", str(ar),
            "-v", str(verbosity),
        ]
        if do_optim:
            cmd.append("-optim")

        logger.info("tier_mmg3d_running", cmd=" ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.warning(
                "tier_mmg3d_binary_error",
                returncode=result.returncode,
                stderr=result.stderr[:500],
            )
            # mmg3d 최적화 실패 시 초기 메쉬로 폴백
            logger.info("tier_mmg3d_fallback_to_initial_mesh")
            writer = PolyMeshWriter()
            mesh_stats = writer.write(tet_v, tet_f, case_dir)
            elapsed = time.monotonic() - t_start
            logger.info("tier_mmg3d_success_initial_fallback", elapsed=elapsed)
            return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)

        # --- Step 4: 최적화된 메쉬 읽기 ---
        if not opt_mesh_path.exists():
            raise RuntimeError(f"mmg3d 출력 파일이 없습니다: {opt_mesh_path}")

        opt_data = meshio.read(str(opt_mesh_path))
        tet_cells = [c for c in opt_data.cells if c.type == "tetra"]

        if not tet_cells:
            raise RuntimeError("mmg3d 출력에 tet 셀이 없습니다.")

        opt_v = np.asarray(opt_data.points, dtype=np.float64)
        opt_f = np.vstack([c.data for c in tet_cells]).astype(np.int64)

        logger.info(
            "tier_mmg3d_optimized_mesh",
            num_points=len(opt_v),
            num_tets=len(opt_f),
            improvement=f"{len(tet_f)}→{len(opt_f)} tets",
        )

        # --- Step 5: polyMesh 변환 ---
        writer = PolyMeshWriter()
        mesh_stats = writer.write(opt_v, opt_f, case_dir)

        # 작업 디렉터리 정리
        import shutil as _shutil
        _shutil.rmtree(str(work_dir), ignore_errors=True)

        elapsed = time.monotonic() - t_start
        logger.info("tier_mmg3d_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
