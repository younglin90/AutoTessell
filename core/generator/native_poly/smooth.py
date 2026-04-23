"""Polyhedral mesh vertex Laplacian smoothing (beta97).

tet_to_poly_dual 이후 경계 근방에서 stretched cell 이 생기는 문제를 개선.
내부 vertex 를 인접 face centroid 의 average 쪽으로 relax 이동시켜
polyhedral cell 의 aspect ratio 를 낮춘다.

알고리즘:
    for iter in range(n_iter):
        for each internal vertex v:
            neighbouring_faces = faces that contain v
            centroid = area-weighted avg of face centroids
            v_new = v + relax * (centroid - v)

boundary vertex (boundary patch face 에 속하는 vertex) 는 이동하지 않음 —
표면 형상 보존.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.utils.logging import get_logger
from core.utils.polymesh_reader import (
    parse_foam_boundary,
    parse_foam_faces,
    parse_foam_labels,
    parse_foam_points,
)
from core.layers.native_bl import _write_points

log = get_logger(__name__)


@dataclass
class SmoothResult:
    success: bool
    elapsed: float
    n_iter_done: int = 0
    max_displacement: float = 0.0
    message: str = ""


def smooth_poly_mesh(
    case_dir: Path,
    *,
    n_iter: int = 3,
    relax: float = 0.3,
    lock_boundary: bool = True,
) -> SmoothResult:
    """polyhedral mesh 의 내부 vertex 를 Laplacian smoothing 으로 이동.

    Args:
        case_dir: OpenFOAM case 디렉터리.
        n_iter: smoothing 반복 횟수 (기본 3).
        relax: 이동 강도 0~1 (기본 0.3 — 보수적).
        lock_boundary: True 면 boundary patch vertex 는 고정 (기본 True).

    Returns:
        SmoothResult.
    """
    t0 = time.perf_counter()
    poly_dir = case_dir / "constant" / "polyMesh"
    if not (poly_dir / "faces").exists():
        return SmoothResult(
            success=False, elapsed=0.0,
            message=f"polyMesh 없음: {poly_dir}",
        )

    pts_raw = parse_foam_points(poly_dir / "points")
    faces_raw = parse_foam_faces(poly_dir / "faces")
    owner_raw = parse_foam_labels(poly_dir / "owner")
    boundary = parse_foam_boundary(poly_dir / "boundary")

    pts = np.array(pts_raw, dtype=np.float64)
    faces = [list(f) for f in faces_raw]
    n_pts = pts.shape[0]

    # boundary vertex 식별 (lock_boundary=True 시 이동 금지)
    locked: set[int] = set()
    if lock_boundary:
        for patch in boundary:
            start = int(patch["startFace"])
            nf = int(patch["nFaces"])
            for fi in range(start, start + nf):
                locked.update(int(v) for v in faces[fi])

    log.info(
        "smooth_poly_mesh_start",
        n_pts=n_pts, n_faces=len(faces),
        n_locked=len(locked), n_iter=n_iter, relax=relax,
    )

    # face centroid + area (면적 가중 평균용)
    def _face_centroid_area(f: list[int]) -> tuple[np.ndarray, float]:
        verts = pts[f]
        c = verts.mean(axis=0)
        if len(f) < 3:
            return c, 0.0
        v0 = verts[0]
        area_vec = np.zeros(3, dtype=np.float64)
        for k in range(1, len(f) - 1):
            area_vec += np.cross(verts[k] - v0, verts[k + 1] - v0)
        area = float(np.linalg.norm(area_vec)) * 0.5
        return c, area

    # vertex → face mapping
    vert_to_faces: dict[int, list[int]] = {v: [] for v in range(n_pts)}
    for fi, f in enumerate(faces):
        for v in f:
            vert_to_faces[int(v)].append(fi)

    max_disp = 0.0
    for it in range(n_iter):
        new_pts = pts.copy()
        it_disp = 0.0
        for v in range(n_pts):
            if v in locked:
                continue
            fl = vert_to_faces[v]
            if not fl:
                continue
            centroids = []
            areas = []
            for fi in fl:
                c, a = _face_centroid_area(faces[fi])
                if a > 1e-30:
                    centroids.append(c)
                    areas.append(a)
            if not centroids:
                continue
            w = np.array(areas, dtype=np.float64)
            target = (np.array(centroids) * w[:, np.newaxis]).sum(axis=0) / w.sum()
            move = relax * (target - pts[v])
            new_pts[v] = pts[v] + move
            d = float(np.linalg.norm(move))
            if d > it_disp:
                it_disp = d
        pts = new_pts
        if it_disp > max_disp:
            max_disp = it_disp
        log.info(
            "smooth_poly_mesh_iter",
            iteration=it + 1, max_displacement=it_disp,
        )

    # 결과 저장
    _write_points(poly_dir / "points", pts)
    elapsed = time.perf_counter() - t0
    return SmoothResult(
        success=True,
        elapsed=elapsed,
        n_iter_done=n_iter,
        max_displacement=max_disp,
        message=(
            f"smooth_poly_mesh OK — {n_iter} iters, "
            f"max_displacement={max_disp:.4g} m, relax={relax}"
        ),
    )
