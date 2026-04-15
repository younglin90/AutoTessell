"""Tier Voronoi Polyhedral: pyvoro 기반 보로노이 다면체 메쉬 생성.

bounding box 내부에 시드 포인트를 배치하고 Voronoi 테셀레이션을 계산하여
완전한 다면체(polyhedral) 셀을 가진 OpenFOAM polyMesh를 생성한다.

특징:
- 각 셀이 보로노이 다면체 (진짜 polyhedral, tet/hex 아님)
- 내부 유동(internal flow)에 최적화
- 균일/불균일 분포 모두 지원
- pyvoro (Voro++ Python bindings) 사용
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from core.generator.polymesh_writer import PolyMeshWriter
from core.schemas import MeshStrategy, TierAttempt
from core.utils.errors import format_missing_dependency_message
from core.utils.logging import get_logger

logger = get_logger(__name__)

TIER_NAME = "tier_voro_poly"


def _sample_interior_points(
    vertices: np.ndarray,
    faces: np.ndarray,
    n_points: int,
    seed: int = 42,
) -> np.ndarray:
    """STL 표면 내부에 시드 포인트를 균일하게 샘플링한다.

    거부 샘플링(rejection sampling): bbox 내 무작위 점 → 내부 판별 반복.

    Args:
        vertices: 표면 메쉬 정점 (N, 3).
        faces: 삼각형 면 (M, 3).
        n_points: 목표 시드 포인트 수.
        seed: 랜덤 시드.

    Returns:
        내부 시드 포인트 배열 (K, 3).
    """
    import trimesh

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    rng = np.random.default_rng(seed)

    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    bbox_size = bbox_max - bbox_min

    points = []
    max_attempts = n_points * 100
    attempt = 0

    while len(points) < n_points and attempt < max_attempts:
        batch = rng.uniform(bbox_min, bbox_max, size=(min(n_points * 4, 10000), 3))
        inside = mesh.contains(batch)
        good = batch[inside]
        points.extend(good.tolist())
        attempt += len(batch)

    pts = np.array(points[:n_points])
    logger.info(
        "voro_seed_points_sampled",
        requested=n_points,
        obtained=len(pts),
        attempts=attempt,
    )
    return pts


def _voronoi_cells_to_polymesh(
    cells: list[dict],
    limits: list[list[float]],
    bbox_min: np.ndarray,
) -> tuple[np.ndarray, list[list[int]], list[list[int]], list[bool]]:
    """pyvoro 셀 목록을 polyMesh 형식으로 변환한다.

    Returns:
        points: (N, 3) 정점 배열
        faces: 각 면의 정점 인덱스 목록 (전역 인덱스)
        cells_face_idx: 각 셀의 면 인덱스 목록
        is_boundary: 각 면이 경계면인지 여부
    """
    all_points: list[list[float]] = []
    point_map: dict[tuple[float, float, float], int] = {}

    all_faces: list[list[int]] = []
    cells_faces: list[list[int]] = []
    face_is_boundary: list[bool] = []

    def _add_point(p: list[float]) -> int:
        key = (round(p[0], 10), round(p[1], 10), round(p[2], 10))
        if key not in point_map:
            point_map[key] = len(all_points)
            all_points.append(p)
        return point_map[key]

    for cell in cells:
        if cell is None:
            cells_faces.append([])
            continue

        cell_verts = cell["vertices"]  # list of [x,y,z]
        cell_faces_info = cell["faces"]  # list of {'vertices': [...], 'adjacent_cell': int}
        cell_face_indices: list[int] = []

        for face_info in cell_faces_info:
            local_v_ids = face_info["vertices"]  # 0-indexed into cell_verts
            adj = face_info["adjacent_cell"]

            global_ids = [_add_point(cell_verts[vi]) for vi in local_v_ids]
            face_idx = len(all_faces)
            all_faces.append(global_ids)
            cell_face_indices.append(face_idx)

            # adj < 0 는 벽면 경계
            face_is_boundary.append(adj < 0)

        cells_faces.append(cell_face_indices)

    points_arr = np.array(all_points, dtype=float) if all_points else np.zeros((0, 3))
    return points_arr, all_faces, cells_faces, face_is_boundary


def _write_voro_polymesh(
    points: np.ndarray,
    faces: list[list[int]],
    cells_faces: list[list[int]],
    face_is_boundary: list[bool],  # kept for API compat, not used for classification
    case_dir: Path,
) -> dict[str, Any]:
    """Voronoi 셀 데이터를 OpenFOAM polyMesh로 직접 기록한다.

    Internal vs boundary classification uses topology (face_cells count), NOT
    the pyvoro `adjacent_cell` flag, which can disagree with the filtered cell
    list and produce invalid topology.
    """
    from core.generator.polymesh_writer import _FOAM_HEADER, _FOOTER

    poly_dir = case_dir / "constant" / "polyMesh"
    poly_dir.mkdir(parents=True, exist_ok=True)

    n_points = len(points)
    n_faces_raw = len(faces)
    n_cells = len(cells_faces)

    # --- Build topology: which cells reference each face ---
    face_cells: dict[int, list[int]] = {}
    for cell_i, face_list in enumerate(cells_faces):
        for fi in face_list:
            if 0 <= fi < n_faces_raw:
                face_cells.setdefault(fi, []).append(cell_i)

    # --- Classify by topology (not adj flag) ---
    internal_faces = sorted(
        [i for i in range(n_faces_raw) if len(face_cells.get(i, [])) == 2],
        key=lambda i: (min(face_cells[i]), max(face_cells[i])),
    )
    boundary_faces = sorted(
        [i for i in range(n_faces_raw) if len(face_cells.get(i, [])) != 2],
        key=lambda i: face_cells[i][0] if face_cells.get(i) else 0,
    )

    n_internal = len(internal_faces)
    n_boundary_faces = len(boundary_faces)
    n_faces = n_internal + n_boundary_faces

    # Reordered: internal first, then boundary
    ordered_ids = internal_faces + boundary_faces

    # --- Build owner/neighbour lists ---
    owner_list: list[int] = []
    neighbour_list: list[int] = []

    for fi in internal_faces:
        cl = face_cells[fi]
        owner_list.append(min(cl))
        neighbour_list.append(max(cl))

    for fi in boundary_faces:
        cl = face_cells.get(fi, [0])
        owner_list.append(cl[0] if cl else 0)

    def _foam_hdr(foam_class: str, object_name: str) -> str:
        return _FOAM_HEADER.format(
            foam_class=foam_class,
            location="constant/polyMesh",
            object_name=object_name,
        )

    # --- Write points ---
    with open(poly_dir / "points", "w") as f:
        f.write(_foam_hdr("vectorField", "points"))
        f.write(f"{n_points}\n(\n")
        for p in points:
            f.write(f"({p[0]:.10g} {p[1]:.10g} {p[2]:.10g})\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write faces ---
    with open(poly_dir / "faces", "w") as f:
        f.write(_foam_hdr("faceList", "faces"))
        f.write(f"{n_faces}\n(\n")
        for fi in ordered_ids:
            face_verts = faces[fi]
            ids = " ".join(str(v) for v in face_verts)
            f.write(f"{len(face_verts)}({ids})\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write owner (with note field) ---
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
    with open(poly_dir / "owner", "w") as f:
        f.write(owner_header)
        f.write(f"{n_faces}\n(\n")
        for o in owner_list:
            f.write(f"{o}\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write neighbour ---
    with open(poly_dir / "neighbour", "w") as f:
        f.write(_foam_hdr("labelList", "neighbour"))
        f.write(f"{n_internal}\n(\n")
        for nb in neighbour_list:
            f.write(f"{nb}\n")
        f.write(")\n")
        f.write(_FOOTER)

    # --- Write boundary ---
    with open(poly_dir / "boundary", "w") as f:
        f.write(_foam_hdr("polyBoundaryMesh", "boundary"))
        if n_boundary_faces > 0:
            f.write("1\n(\n")
            f.write("    walls\n    {\n")
            f.write("        type wall;\n")
            f.write(f"        nFaces {n_boundary_faces};\n")
            f.write(f"        startFace {n_internal};\n")
            f.write("    }\n)\n")
        else:
            f.write("0\n(\n)\n")
        f.write(_FOOTER)

    return {
        "n_points": n_points,
        "n_faces": n_faces,
        "n_cells": n_cells,
        "n_internal_faces": n_internal,
        "n_boundary_faces": n_boundary_faces,
    }


class TierVoroPolyGenerator:
    """Voro++ 기반 Voronoi 다면체 메쉬 생성기.

    pyvoro를 사용하여 STL 표면 내부에 Voronoi 테셀레이션을 생성한다.
    각 셀은 진정한 다면체(polyhedral)이며 OpenFOAM polyMesh로 출력된다.

    내부 유동(internal flow) 해석에 적합:
    - 복잡한 내부 기하학
    - 셀 수 최소화가 필요한 경우
    - 다면체 메쉬 특성이 필요한 경우
    """

    def run(
        self,
        strategy: MeshStrategy,
        preprocessed_path: Path,
        case_dir: Path,
    ) -> TierAttempt:
        """Voronoi 폴리헤드럴 파이프라인을 실행한다."""
        t_start = time.monotonic()
        logger.info("tier_voro_poly_start", preprocessed_path=str(preprocessed_path))

        # pyvoro import 확인
        try:
            import pyvoro  # noqa: F401
        except ImportError as exc:
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=format_missing_dependency_message(
                    dependency="pyvoro-mm",
                    fallback="tier_jigsaw_fallback",
                    action="pip install pyvoro-mm",
                    detail=str(exc),
                ),
            )

        if not preprocessed_path.exists():
            elapsed = time.monotonic() - t_start
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"전처리 파일 없음: {preprocessed_path}",
            )

        try:
            import pyvoro
            import trimesh as _trimesh

            params = strategy.tier_specific_params
            quality_level = getattr(strategy, "quality_level", "standard")
            if hasattr(quality_level, "value"):
                quality_level = quality_level.value

            # 시드 포인트 수 결정
            n_seeds_map = {"draft": 500, "standard": 2000, "fine": 8000}
            n_seeds = int(params.get("voro_n_seeds", n_seeds_map.get(quality_level, 2000)))

            # STL 로드
            surf = _trimesh.load(str(preprocessed_path), force="mesh")
            vertices = np.array(surf.vertices)
            faces = np.array(surf.faces)

            bbox_min = vertices.min(axis=0)
            bbox_max = vertices.max(axis=0)
            pad = (bbox_max - bbox_min) * 0.01  # 1% 패딩

            limits = [
                [float(bbox_min[0] - pad[0]), float(bbox_max[0] + pad[0])],
                [float(bbox_min[1] - pad[1]), float(bbox_max[1] + pad[1])],
                [float(bbox_min[2] - pad[2]), float(bbox_max[2] + pad[2])],
            ]

            # 내부 시드 포인트 샘플링
            logger.info("voro_sampling_seeds", n_seeds=n_seeds)
            seed_points = _sample_interior_points(vertices, faces, n_seeds)

            if len(seed_points) < 10:
                elapsed = time.monotonic() - t_start
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    error_message=f"내부 시드 포인트 부족: {len(seed_points)} < 10",
                )

            # 분산(dispersion) 파라미터: bbox 대각선의 일부
            bbox_diag = np.linalg.norm(bbox_max - bbox_min)
            dispersion = float(bbox_diag / max(1, int(n_seeds ** (1 / 3)) - 1))

            logger.info(
                "voro_tessellating",
                n_seeds=len(seed_points),
                dispersion=f"{dispersion:.4f}",
                limits=limits,
            )

            # Voronoi 테셀레이션
            cells = pyvoro.compute_voronoi(
                seed_points.tolist(),
                limits,
                dispersion,
            )

            # 유효 셀 수 확인
            valid_cells = [c for c in cells if c is not None and len(c.get("vertices", [])) >= 4]
            logger.info(
                "voro_tessellation_done",
                total_cells=len(cells),
                valid_cells=len(valid_cells),
            )

            if len(valid_cells) < 5:
                elapsed = time.monotonic() - t_start
                return TierAttempt(
                    tier=TIER_NAME,
                    status="failed",
                    time_seconds=elapsed,
                    error_message=f"유효 Voronoi 셀 부족: {len(valid_cells)}",
                )

            # 유효 셀만 사용
            cells_to_write = valid_cells

            # polyMesh 변환 및 저장
            points_arr, all_faces, cells_faces, face_is_boundary = _voronoi_cells_to_polymesh(
                cells_to_write, limits, bbox_min
            )

            mesh_stats = _write_voro_polymesh(
                points_arr, all_faces, cells_faces, face_is_boundary, case_dir
            )
            PolyMeshWriter._ensure_system_files(case_dir)

            elapsed = time.monotonic() - t_start
            logger.info(
                "tier_voro_poly_success",
                elapsed=elapsed,
                n_cells=mesh_stats["n_cells"],
                n_points=mesh_stats["n_points"],
            )

            return TierAttempt(
                tier=TIER_NAME,
                status="success",
                time_seconds=elapsed,
            )

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.exception("tier_voro_poly_failed", error=str(exc))
            return TierAttempt(
                tier=TIER_NAME,
                status="failed",
                time_seconds=elapsed,
                error_message=f"Tier Voro Poly 실패: {exc}",
            )
