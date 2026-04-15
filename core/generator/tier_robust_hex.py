"""Tier Robust Pure Hex: 옥트리 기반 순수 Hex 메쉬 생성기.

Feature-Preserving Octree Hex Meshing (RobustPureHexMeshing) 바이너리를
subprocess로 호출해 순수 all-hexahedron 메쉬를 생성한다.

참고:
  "Robust Structure Simplification for Hex Re-meshing"
  https://github.com/Cotrik/CotrikMesh (Feature-Preserving Octree variant)

CLI: RobustPureHexMeshing --ch GRID --in input.obj --out output.vtk --n num_cells

결과:
  - 순수 hexahedron 셀 (all-hex polyMesh, quad 면 그대로 유지)
  - polyMesh 변환 (_voxel_hex_to_polymesh 사용)

Tier 파라미터 (strategy.tier_specific_params):
    robust_hex_n_cells (int):
        옥트리 세분화 레벨 (cells per edge). 클수록 촘촘, 느림.
        품질별 기본값: draft=2 (~수초), standard=3 (~수분), fine=4 (~수십분)
        권장 범위: 2~5. n=2: 매우 성긴 hex, n=5: 매우 촘촘한 hex.
    robust_hex_hausdorff (float, default=None):
        Hausdorff 비율 임계값 (None=기본값 사용).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from core.generator.tier_cinolib_hex import _voxel_hex_to_polymesh
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_robust_hex"
_BIN_NAME = "RobustPureHexMeshing"
_WRAPPER_NAME = "robust_hex_mesh"


def _find_binary() -> Path | None:
    """RobustPureHexMeshing 실행 파일을 찾아 반환한다."""
    import sys

    project_bin_dir = Path(__file__).resolve().parents[2] / "bin"

    if sys.platform == "win32":
        import os
        for name in (_BIN_NAME, _WRAPPER_NAME):
            for ext in (".exe", ""):
                p = project_bin_dir / (name + ext)
                if p.exists():
                    return p
        for win_dir in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "AutoTessell" / "bin",
            Path(r"C:\AutoTessell\bin"),
        ):
            for name in (_BIN_NAME, _WRAPPER_NAME):
                p = win_dir / (name + ".exe")
                if p.exists():
                    return p
    else:
        # 1) AutoTessell bin/ 디렉터리
        for name in (_BIN_NAME, _WRAPPER_NAME):
            p = project_bin_dir / name
            if p.exists():
                return p

    # PATH
    found = shutil.which(_BIN_NAME) or shutil.which(_WRAPPER_NAME)
    if found:
        return Path(found)
    return None


class TierRobustHexGenerator:
    """Feature-Preserving Octree 기반 순수 All-Hex 메쉬 생성기.

    OBJ 입력 → RobustPureHexMeshing CLI → VTK 출력 → polyMesh 변환.
    STL은 자동으로 OBJ로 변환 후 처리한다.

    주의: n_cells >= 4 이면 수분 이상 소요될 수 있다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_robust_hex_start", preprocessed_path=str(preprocessed_path))

        # 바이너리 확인
        binary = _find_binary()
        if binary is None:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    "RobustPureHexMeshing 바이너리를 찾을 수 없습니다. "
                    "Feature-Preserving-Octree-Hex-Meshing을 빌드하고 "
                    "bin/에 복사하세요."
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

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일을 찾을 수 없습니다: {preprocessed_path}",
            )

        try:
            return self._run_pipeline(
                binary=binary,
                strategy=strategy,
                preprocessed_path=preprocessed_path,
                case_dir=case_dir,
                t_start=t_start,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_robust_hex_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"RobustPureHexMeshing 실행 실패: {exc}",
            )

    def _run_pipeline(
        self,
        binary: Path,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
        t_start: float,
    ) -> TierAttempt:
        import meshio
        import trimesh

        params = strategy.tier_specific_params
        quality_level = getattr(strategy, "quality_level", "standard")
        if hasattr(quality_level, "value"):
            quality_level = quality_level.value
        _n_cells_default = {"draft": 2, "standard": 3, "fine": 4}
        n_cells: int = int(params.get("robust_hex_n_cells", _n_cells_default.get(quality_level, 3)))

        # Hausdorff 임계값: 클수록 표면 근사 허용치↑, 반복 루프 감소
        # draft=0.05(5%), standard=0.02(2%), fine=0.005(0.5%, 기본값)
        _hausdorff_default = {"draft": 0.05, "standard": 0.02, "fine": 0.005}
        hausdorff: float = float(params.get("robust_hex_hausdorff",
                                            _hausdorff_default.get(quality_level, 0.02)))

        # SLIM 최적화 반복 횟수 (--Iter): draft=1, standard=2, fine=3(기본값)
        _iter_default = {"draft": 1, "standard": 2, "fine": 3}
        slim_iter: int = int(params.get("robust_hex_slim_iter",
                                        _iter_default.get(quality_level, 2)))

        # 품질별 바이너리 실행 타임아웃 (초)
        _timeout_map = {"draft": 120, "standard": 360, "fine": 900}
        bin_timeout: int = int(params.get("robust_hex_timeout", _timeout_map.get(quality_level, 360)))

        logger.info(
            "tier_robust_hex_params",
            n_cells=n_cells, hausdorff=hausdorff, slim_iter=slim_iter,
        )

        work_dir = case_dir / "_robust_hex_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # STL → OBJ 변환 (RobustPureHexMeshing은 OBJ만 지원)
        obj_path = work_dir / "input.obj"
        surf = trimesh.load(str(preprocessed_path), force="mesh")
        surf.export(str(obj_path))
        logger.info("tier_robust_hex_stl2obj", obj_path=str(obj_path))

        # 출력 경로
        out_base = work_dir / "output"
        out_vtk = Path(str(out_base) + ".vtk")

        # 실행 명령
        bin_dir = binary.parent
        env_override = {"LD_LIBRARY_PATH": str(bin_dir)}
        import os
        env = {**os.environ, **env_override}

        cmd = [
            str(binary),
            "--ch", "GRID",
            "--in", str(obj_path),
            "--out", str(out_base) + ".mesh",
            "--n", str(n_cells),
            "--h", str(hausdorff),    # Hausdorff 임계값 (루프 종료 조건)
            "--Iter", str(slim_iter), # SLIM 최적화 반복 횟수
            # --e (edge_length_ratio/octree depth)는 주지 않음:
            # 값에 따라 octree 해상도가 바뀌어 오히려 느려지는 부작용 있음
        ]

        logger.info("tier_robust_hex_running", cmd=" ".join(cmd), timeout=bin_timeout)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=bin_timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"RobustPureHexMeshing이 {bin_timeout}초 내에 완료되지 않았습니다. "
                f"n_cells={n_cells}을 줄이거나 robust_hex_timeout 파라미터를 늘리세요."
            )

        # RobustPureHexMeshing은 성공해도 returncode가 비표준일 수 있음
        if result.returncode != 0:
            logger.warning(
                "tier_robust_hex_nonzero_exit",
                returncode=result.returncode,
                stderr=result.stderr[:300],
            )

        # VTK 출력 확인 (바이너리가 자동으로 .vtk도 생성)
        if not out_vtk.exists():
            # 다른 확장자 탐색
            vtk_candidates = list(work_dir.glob("*.vtk"))
            if vtk_candidates:
                out_vtk = vtk_candidates[0]
            else:
                raise RuntimeError(
                    f"RobustPureHexMeshing이 VTK 출력을 생성하지 않았습니다. "
                    f"stdout: {result.stdout[-300:]}"
                )

        # VTK 읽기
        mesh_data = meshio.read(str(out_vtk))
        hex_cells = [c for c in mesh_data.cells if c.type == "hexahedron"]
        if not hex_cells:
            raise RuntimeError(
                f"VTK 출력에 hexahedron 셀이 없습니다. "
                f"cells: {[(c.type, len(c.data)) for c in mesh_data.cells]}"
            )

        hex_v = np.asarray(mesh_data.points, dtype=np.float64)
        hex_f = np.vstack([c.data for c in hex_cells]).astype(np.int64)

        logger.info(
            "tier_robust_hex_mesh_built",
            num_points=len(hex_v),
            num_hexahedra=len(hex_f),
        )

        # polyMesh 직접 변환: hex 쿼드 면을 그대로 유지 (tet 분해 없음)
        mesh_stats = _voxel_hex_to_polymesh(hex_v, hex_f, case_dir)

        # 작업 디렉터리 정리
        shutil.rmtree(str(work_dir), ignore_errors=True)

        elapsed = time.monotonic() - t_start
        logger.info("tier_robust_hex_success", elapsed=elapsed, mesh_stats=mesh_stats)
        return TierAttempt(tier=TIER_NAME, status="success", time_seconds=elapsed)
