"""Tier CinoLib Hex: voxel 기반 hex 메싱 (cinolib C++ 확장).

cinolib의 INSIDE + BOUNDARY 복셀을 8절점 헥사헤드럴 셀로 변환한다.
복셀 해상도(resolution)가 클수록 메싱이 세밀하지만 메모리를 더 사용한다.

.so 파일이 없으면 최초 사용 시 자동으로 빌드한다 (cmake + make).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_cinolib_hex"

_CORE_DIR  = Path(__file__).resolve().parents[2] / "auto_tessell_core"
_BUILD_DIR = _CORE_DIR / "build"

# cinolib 저장소 경로 (없으면 자동 clone)
_CINOLIB_REPO = "https://github.com/mlivesu/cinolib.git"
_CINOLIB_DIR  = Path("/tmp/hexmesh_build/cinolib")


def _ensure_cinolib_cloned() -> bool:
    """cinolib 저장소가 없으면 clone한다. 성공 여부를 반환한다."""
    if (_CINOLIB_DIR / "include" / "cinolib").exists():
        return True
    if shutil.which("git") is None:
        logger.warning("cinolib_clone_skip", reason="git not found")
        return False
    try:
        _CINOLIB_DIR.parent.mkdir(parents=True, exist_ok=True)
        logger.info("cinolib_cloning", repo=_CINOLIB_REPO, dst=str(_CINOLIB_DIR))
        subprocess.run(
            ["git", "clone", "--depth=1", _CINOLIB_REPO, str(_CINOLIB_DIR)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return True
    except Exception as exc:
        logger.warning("cinolib_clone_failed", error=str(exc))
        return False


def _build_cinolib_hex() -> bool:
    """cmake + make 로 cinolib_hex.so 를 빌드한다. 성공 여부를 반환한다."""
    if shutil.which("cmake") is None or shutil.which("g++") is None:
        logger.warning("cinolib_build_skip", reason="cmake or g++ not found")
        return False

    try:
        pybind11_dir = subprocess.check_output(
            [sys.executable, "-c", "import pybind11; print(pybind11.get_cmake_dir())"],
            text=True,
        ).strip()
    except Exception:
        logger.warning("cinolib_build_skip", reason="pybind11 not installed")
        return False

    _BUILD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("cinolib_hex_building", build_dir=str(_BUILD_DIR))

        # cmake configure
        subprocess.run(
            [
                "cmake", str(_CORE_DIR),
                "-DCMAKE_BUILD_TYPE=Release",
                f"-Dpybind11_DIR={pybind11_dir}",
                "-Wno-dev",
            ],
            cwd=str(_BUILD_DIR),
            check=True,
            capture_output=True,
            timeout=120,
        )

        # cmake build (cinolib_hex target만)
        import os
        nproc = os.cpu_count() or 4
        subprocess.run(
            ["cmake", "--build", ".", "--target", "cinolib_hex", f"-j{nproc}"],
            cwd=str(_BUILD_DIR),
            check=True,
            capture_output=True,
            timeout=300,
        )

        logger.info("cinolib_hex_build_success")
        return True

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="replace")[-500:]
        logger.warning("cinolib_hex_build_failed", stderr=stderr)
        return False
    except Exception as exc:
        logger.warning("cinolib_hex_build_failed", error=str(exc))
        return False


def _load_cinolib_hex():
    """cinolib_hex 확장 모듈을 로드한다. 없으면 자동 빌드 후 재시도한다."""
    if "cinolib_hex" in sys.modules:
        return sys.modules["cinolib_hex"]

    def _try_load_so() -> object | None:
        so_files = list(_BUILD_DIR.glob("cinolib_hex*.so"))
        if not so_files:
            return None
        spec = importlib.util.spec_from_file_location("cinolib_hex", so_files[0])
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        sys.modules["cinolib_hex"] = mod
        return mod

    # 1차: 이미 빌드된 .so 탐색
    mod = _try_load_so()
    if mod is not None:
        return mod

    # 2차: 시스템 PYTHONPATH 시도
    try:
        import cinolib_hex as _m
        return _m
    except ImportError:
        pass

    # 3차: 자동 빌드
    logger.info("cinolib_hex_not_found_auto_building")
    if _ensure_cinolib_cloned() and _build_cinolib_hex():
        return _try_load_so()

    return None


class TierCinolibHexGenerator:
    """cinolib C++ 확장 기반 voxel-to-hex 메시 생성기.

    STL 표면을 voxelize한 뒤 INSIDE + BOUNDARY 복셀을 hex 셀로 변환한다.
    결과는 OpenFOAM polyMesh로 내보낸다.
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        t_start = time.monotonic()
        logger.info("tier_cinolib_hex_start", preprocessed_path=str(preprocessed_path))

        # 확장 모듈 로드
        mod = _load_cinolib_hex()
        if mod is None:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=(
                    "cinolib_hex 확장 모듈을 찾을 수 없습니다. "
                    f"auto_tessell_core/ 를 cmake --build 로 빌드하세요. "
                    f"빌드 경로: {_BUILD_DIR}"
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
            import trimesh as _trimesh

            # 표면 메시 로드
            surf: _trimesh.Trimesh = _trimesh.load(str(preprocessed_path), force="mesh")  # type: ignore[assignment]

            # resolution 결정 (quality_level에 따라)
            params = strategy.tier_specific_params
            quality_level = getattr(strategy, "quality_level", "standard")
            if hasattr(quality_level, "value"):
                quality_level = quality_level.value

            _resolution_map = {"draft": 30, "standard": 50, "fine": 80}
            resolution = params.get(
                "cinolib_hex_resolution",
                _resolution_map.get(quality_level, 50),
            )

            logger.info("tier_cinolib_hex_voxelize", resolution=resolution)

            vertices = np.asarray(surf.vertices, dtype=np.float64)
            faces = np.asarray(surf.faces, dtype=np.int32)

            # C++ cinolib voxel→hex 변환 호출
            hex_verts, hex_cells = mod.voxel_hex_mesh(vertices, faces, int(resolution))

            n_verts = len(hex_verts)
            n_cells = len(hex_cells)
            logger.info("tier_cinolib_hex_mesh_built", n_verts=n_verts, n_cells=n_cells)

            if n_verts == 0 or n_cells == 0:
                raise RuntimeError("cinolib_hex가 빈 메시를 반환했습니다.")

            # hex_cells: (C, 8) — 8절점 hex 셀
            # PolyMeshWriter는 tet (4-node) 셀을 기대하므로
            # hex를 Kuhn 분해로 6 tet로 변환
            tets = _hex_to_tet(hex_cells)

            writer = PolyMeshWriter()
            mesh_stats = writer.write(hex_verts, tets, case_dir)

            elapsed = time.monotonic() - t_start
            logger.info("tier_cinolib_hex_success", elapsed=elapsed, mesh_stats=mesh_stats)

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_cinolib_hex_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier CinoLib Hex 실행 실패: {exc}",
            )


def _hex_to_tet(hex_cells: np.ndarray) -> np.ndarray:
    """Kuhn 분해: 각 hex(8 vertices)를 6개의 tet으로 분해.

    Args:
        hex_cells: (C, 8) int array — hex cell vertex indices.

    Returns:
        (C*6, 4) int array — tet connectivity.
    """
    # 표준 Kuhn 분해 패턴 (절점 순서 가정: 0-7 아래->위 순서)
    _KUHN_TETS = np.array(
        [
            [0, 1, 3, 7],
            [0, 1, 5, 7],
            [1, 2, 3, 7],
            [1, 2, 6, 7],
            [1, 4, 5, 7],
            [1, 4, 6, 7],
        ],
        dtype=np.int64,
    )

    C = len(hex_cells)
    tets = np.empty((C * 6, 4), dtype=np.int64)
    for i, pattern in enumerate(_KUHN_TETS):
        tets[i::6] = hex_cells[:, pattern]

    return tets
