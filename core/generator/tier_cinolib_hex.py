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
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter, _FOAM_HEADER, _FOOTER
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

            # hex_cells: (C, 8) — 8절점 hex 셀 → 직접 polyhedral polyMesh로 출력
            mesh_stats = _voxel_hex_to_polymesh(hex_verts, hex_cells, case_dir)

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


def _quad_ccw(quad_pts: np.ndarray, outward_dir: np.ndarray) -> list[int]:
    """4점 쿼드를 외부 법선이 outward_dir과 같은 방향이 되도록 CCW 정렬.

    Args:
        quad_pts: (4, 3) — 4개 꼭짓점 좌표 (인덱스 0~3).
        outward_dir: (3,) — 예상 외부 법선 방향.

    Returns:
        길이 4의 정수 리스트 — CCW 정렬된 로컬 인덱스.
    """
    centroid = quad_pts.mean(axis=0)

    # 평면에 두 개의 기저 벡터를 구성
    v0 = quad_pts[0] - centroid
    normal_ref = outward_dir / (np.linalg.norm(outward_dir) + 1e-30)

    # 첫 번째 기저: v0 방향 (centroid → pt0)
    e1 = v0 - np.dot(v0, normal_ref) * normal_ref
    e1_len = np.linalg.norm(e1)
    if e1_len < 1e-14:
        # 모든 점이 겹침 — 임의로 반환
        return list(range(4))
    e1 = e1 / e1_len
    e2 = np.cross(normal_ref, e1)

    # 각 꼭짓점을 평면에 투영해 각도를 계산
    angles = []
    for i, pt in enumerate(quad_pts):
        d = pt - centroid
        angle = np.arctan2(np.dot(d, e2), np.dot(d, e1))
        angles.append((angle, i))

    # CCW 정렬 (각도 오름차순)
    angles.sort()
    order = [a[1] for a in angles]

    # 법선 방향 확인 — 반대면 뒤집기
    p0, p1, p2 = quad_pts[order[0]], quad_pts[order[1]], quad_pts[order[2]]
    normal_computed = np.cross(p1 - p0, p2 - p0)
    if np.dot(normal_computed, outward_dir) < 0:
        order = order[::-1]

    return order


def _voxel_hex_to_polymesh(
    hex_verts: np.ndarray,
    hex_cells: np.ndarray,
    case_dir: Path,
) -> dict[str, Any]:
    """축 정렬 hex(voxel) 메시를 OpenFOAM polyMesh로 직접 변환.

    각 hex 셀의 8절점에서 6개의 쿼드 면을 추출하고,
    공유면(내부)/단독면(경계)을 분류해 polyMesh 파일을 생성한다.

    Args:
        hex_verts: (N, 3) float array — 정점 좌표.
        hex_cells: (C, 8) int array — hex 셀 연결성 (0-based).
        case_dir: OpenFOAM 케이스 디렉터리.

    Returns:
        메시 통계 dict (num_cells, num_points, num_faces, num_internal_faces).
    """
    hex_verts = np.asarray(hex_verts, dtype=np.float64)
    hex_cells = np.asarray(hex_cells, dtype=np.int64)

    # --- 각 hex 셀의 6개 쿼드 면 로컬 패턴 ---
    # OpenFOAM hex 절점 순서 가정 (cinolib 출력과 맞춤):
    #   0-3: 하면(z-low), 4-7: 상면(z-high), 아래→위 동일 XY 순서
    #
    #   3---2       7---6
    #   |   |  →   |   |
    #   0---1       4---5
    #
    # 6개 면: -z, +z, -y, +y, -x, +x
    _HEX_QUAD_LOCAL = [
        (0, 3, 2, 1),  # -Z face  (하면: 외부 법선 -Z)
        (4, 5, 6, 7),  # +Z face  (상면: 외부 법선 +Z)
        (0, 1, 5, 4),  # -Y face
        (3, 7, 6, 2),  # +Y face
        (0, 4, 7, 3),  # -X face
        (1, 2, 6, 5),  # +X face
    ]

    # face_map: frozenset(4 global vert indices) → [(cell_id, ordered_quad_global_idx)]
    face_map: dict[frozenset, list[tuple[int, tuple[int, int, int, int]]]] = defaultdict(list)

    for cell_id, cell in enumerate(hex_cells):
        cell_centroid = hex_verts[cell].mean(axis=0)

        for local_quad in _HEX_QUAD_LOCAL:
            g = tuple(int(cell[i]) for i in local_quad)  # (4,) global indices
            quad_pts = hex_verts[list(g)]

            face_centroid = quad_pts.mean(axis=0)
            outward_dir = face_centroid - cell_centroid

            # CCW 정렬 (법선이 셀 바깥쪽)
            order = _quad_ccw(quad_pts, outward_dir)
            oriented = tuple(g[o] for o in order)

            key = frozenset(g)
            face_map[key].append((cell_id, oriented))

    # 내부면 (2개 셀) vs 경계면 (1개 셀) 분류
    internal: list[tuple[int, int, tuple]] = []   # (owner, neighbour, oriented_verts)
    boundary: list[tuple[int, tuple]] = []          # (owner, oriented_verts)

    for key, entries in face_map.items():
        if len(entries) == 2:
            c0, v0 = entries[0]
            c1, v1 = entries[1]
            own = min(c0, c1)
            nbr = max(c0, c1)
            # 면 방향은 owner(더 작은 ID 셀) 기준 외부 법선
            verts = v0 if c0 == own else v1
            internal.append((own, nbr, verts))
        else:
            cell_id, verts = entries[0]
            boundary.append((cell_id, verts))

    internal.sort(key=lambda x: (x[0], x[1]))
    boundary.sort(key=lambda x: x[0])

    n_internal = len(internal)
    n_boundary = len(boundary)
    n_faces = n_internal + n_boundary
    n_cells = len(hex_cells)
    n_points = len(hex_verts)

    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    # --- points ---
    lines = [_FOAM_HEADER.format(
        foam_class="vectorField",
        location="constant/polyMesh",
        object_name="points",
    )]
    lines.append(f"{n_points}")
    lines.append("(")
    for v in hex_verts:
        lines.append(f"({v[0]:.10g} {v[1]:.10g} {v[2]:.10g})")
    lines.append(")")
    lines.append(_FOOTER)
    (poly_dir / "points").write_text("\n".join(lines))

    # --- faces ---
    all_faces: list[tuple] = []
    owner_list: list[int] = []
    neighbour_list: list[int] = []

    for own, nbr, verts in internal:
        all_faces.append(verts)
        owner_list.append(own)
        neighbour_list.append(nbr)

    for own, verts in boundary:
        all_faces.append(verts)
        owner_list.append(own)

    lines = [_FOAM_HEADER.format(
        foam_class="faceList",
        location="constant/polyMesh",
        object_name="faces",
    )]
    lines.append(f"{n_faces}")
    lines.append("(")
    for f in all_faces:
        vert_str = " ".join(str(v) for v in f)
        lines.append(f"{len(f)}({vert_str})")
    lines.append(")")
    lines.append(_FOOTER)
    (poly_dir / "faces").write_text("\n".join(lines))

    # --- owner ---
    note = (
        f"nPoints:{n_points}  nCells:{n_cells}  "
        f"nFaces:{n_faces}  nInternalFaces:{n_internal}"
    )
    owner_header = _FOAM_HEADER.format(
        foam_class="labelList",
        location="constant/polyMesh",
        object_name="owner",
    ).replace(
        "    object      owner;",
        f"    note        \"{note}\";\n    object      owner;",
    )
    lines = [owner_header]
    lines.append(f"{len(owner_list)}")
    lines.append("(")
    for o in owner_list:
        lines.append(str(o))
    lines.append(")")
    lines.append(_FOOTER)
    (poly_dir / "owner").write_text("\n".join(lines))

    # --- neighbour ---
    lines = [_FOAM_HEADER.format(
        foam_class="labelList",
        location="constant/polyMesh",
        object_name="neighbour",
    )]
    lines.append(f"{n_internal}")
    lines.append("(")
    for nb in neighbour_list:
        lines.append(str(nb))
    lines.append(")")
    lines.append(_FOOTER)
    (poly_dir / "neighbour").write_text("\n".join(lines))

    # --- boundary ---
    lines = [_FOAM_HEADER.format(
        foam_class="polyBoundaryMesh",
        location="constant/polyMesh",
        object_name="boundary",
    )]
    lines.append("1")
    lines.append("(")
    lines.append("    defaultWall")
    lines.append("    {")
    lines.append("        type wall;")
    lines.append(f"        nFaces {n_boundary};")
    lines.append(f"        startFace {n_internal};")
    lines.append("    }")
    lines.append(")")
    lines.append(_FOOTER)
    (poly_dir / "boundary").write_text("\n".join(lines))

    # system/ 파일 생성
    PolyMeshWriter._ensure_system_files(case_dir)

    stats = {
        "num_cells": n_cells,
        "num_points": n_points,
        "num_faces": n_faces,
        "num_internal_faces": n_internal,
    }
    logger.info("voxel_hex_polymesh_written", **stats)
    return stats
