"""경계 패치 자동 분류기.

메쉬의 boundary 패치를 분석하여 inlet/outlet/wall/symmetry를 자동 추정한다.
외부 유동의 경우 도메인 경계면의 위치와 법선 방향으로 판단한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_points,
)

log = get_logger(__name__)


def classify_boundaries(
    case_dir: Path,
    flow_type: str = "external",
    flow_direction: int = 0,
) -> list[dict[str, Any]]:
    """경계 패치를 자동 분류한다.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        flow_type: "external" 또는 "internal".
        flow_direction: 주요 유동 방향 축 (0=x, 1=y, 2=z).

    Returns:
        패치별 분류 결과 리스트.
        [{"name": "patch0", "type": "inlet", "nFaces": 100, ...}, ...]
    """
    poly_dir = case_dir / "constant" / "polyMesh"
    if not poly_dir.exists():
        return []

    try:
        points = np.array(parse_foam_points(poly_dir / "points"))
        faces = parse_foam_faces(poly_dir / "faces")
        boundary = parse_foam_boundary(poly_dir / "boundary")
    except Exception as exc:
        log.warning("boundary_classification_failed", error=str(exc))
        return []

    if len(points) == 0 or len(faces) == 0 or len(boundary) == 0:
        return []

    # 전체 메쉬 BBox
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    bbox_size = bbox_max - bbox_min

    results: list[dict[str, Any]] = []

    for patch in boundary:
        name: str = patch.get("name", "unknown")
        start_face: int = patch["startFace"]
        n_faces: int = patch["nFaces"]

        if n_faces == 0:
            results.append({"name": name, "type": "empty", "nFaces": 0})
            continue

        # 패치 면들의 중심점과 법선 계산
        patch_centers = []
        patch_normals = []
        for i in range(start_face, min(start_face + n_faces, len(faces))):
            face = faces[i]
            if len(face) < 3:
                continue
            verts = points[face]
            center = verts.mean(axis=0)
            # Face normal (cross product of first two edges)
            e1 = verts[1] - verts[0]
            e2 = verts[2] - verts[0]
            normal = np.cross(e1, e2)
            mag = np.linalg.norm(normal)
            if mag > 0:
                normal /= mag
            patch_centers.append(center)
            patch_normals.append(normal)

        if not patch_centers:
            results.append({"name": name, "type": "wall", "nFaces": n_faces})
            continue

        centers = np.array(patch_centers)
        normals = np.array(patch_normals)

        # 패치 중심의 평균 위치
        avg_center = centers.mean(axis=0)
        avg_normal = normals.mean(axis=0)
        avg_normal_mag = np.linalg.norm(avg_normal)
        if avg_normal_mag > 0:
            avg_normal /= avg_normal_mag

        # 분류 로직
        patch_type = _classify_patch(
            name, avg_center, avg_normal, bbox_min, bbox_max, bbox_size,
            flow_type, flow_direction, n_faces,
        )

        results.append({
            "name": name,
            "type": patch_type,
            "nFaces": n_faces,
            "center": avg_center.tolist(),
            "normal": avg_normal.tolist(),
        })

    log.info(
        "boundary_classified",
        patches=[(r["name"], r["type"]) for r in results],
    )
    return results


def _classify_patch(
    name: str,
    center: np.ndarray,
    normal: np.ndarray,
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    bbox_size: np.ndarray,
    flow_type: str,
    flow_dir: int,
    n_faces: int,
) -> str:
    """단일 패치를 분류한다."""
    # 이름 기반 힌트 (우선순위 높음)
    name_lower = name.lower()
    if any(kw in name_lower for kw in ("inlet", "inflow", "input")):
        return "inlet"
    if any(kw in name_lower for kw in ("outlet", "outflow", "output", "exit")):
        return "outlet"
    if any(kw in name_lower for kw in ("wall", "body", "surface", "object")):
        return "wall"
    if any(kw in name_lower for kw in ("sym", "symmetry")):
        return "symmetryPlane"
    if "default" in name_lower:
        return "wall"

    if flow_type == "external":
        return _classify_external(center, normal, bbox_min, bbox_max, bbox_size, flow_dir)
    else:
        return _classify_internal(center, normal, bbox_min, bbox_max, bbox_size, flow_dir, n_faces)


def _classify_external(
    center: np.ndarray,
    normal: np.ndarray,
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    bbox_size: np.ndarray,
    flow_dir: int,
) -> str:
    """외부 유동 패치 분류.

    도메인 경계면 중:
    - flow_dir 축 최소면 → inlet
    - flow_dir 축 최대면 → outlet
    - 나머지 → wall (또는 farfield)
    - 도메인 중심 근처 → body (wall)
    """
    tol = 0.05  # bbox 대비 5% 이내

    # 도메인 경계면 판단 (BBox 표면 근처인지)
    rel_pos = (center - bbox_min) / np.maximum(bbox_size, 1e-10)

    # 도메인 최소면 (flow 방향)
    if rel_pos[flow_dir] < tol:
        return "inlet"
    # 도메인 최대면 (flow 방향)
    if rel_pos[flow_dir] > (1.0 - tol):
        return "outlet"

    # 도메인 경계면 (측면)
    for axis in range(3):
        if axis == flow_dir:
            continue
        if rel_pos[axis] < tol or rel_pos[axis] > (1.0 - tol):
            return "wall"

    # 도메인 내부 → 물체 표면
    return "wall"


def _classify_internal(
    center: np.ndarray,
    normal: np.ndarray,
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    bbox_size: np.ndarray,
    flow_dir: int,
    n_faces: int,
) -> str:
    """내부 유동 패치 분류.

    - 유동 방향 축 양단 → inlet/outlet
    - 나머지 → wall
    """
    tol = 0.05
    rel_pos = (center - bbox_min) / np.maximum(bbox_size, 1e-10)

    if rel_pos[flow_dir] < tol:
        return "inlet"
    if rel_pos[flow_dir] > (1.0 - tol):
        return "outlet"

    return "wall"
