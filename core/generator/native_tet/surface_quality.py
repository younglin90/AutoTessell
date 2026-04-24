"""R140 — 결과 tet boundary 의 triangle 품질 리포트.

surface triangle quality (aspect, min angle) 분포 통계. mesh visualization /
bench dashboard 용.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.generator.native_tet.hausdorff import _tet_boundary_faces


@dataclass
class SurfaceQualityReport:
    n_faces: int
    min_angle_deg: float
    mean_min_angle_deg: float
    p5_min_angle_deg: float
    max_aspect: float
    mean_aspect: float
    p95_aspect: float


def _triangle_angles_deg(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """각 triangle 의 3 corner angle (deg)."""
    A = V[F[:, 0]]; B = V[F[:, 1]]; C = V[F[:, 2]]

    def _corner(P, Q, R):
        e1 = Q - P; e2 = R - P
        n1 = np.linalg.norm(e1, axis=1)
        n2 = np.linalg.norm(e2, axis=1)
        denom = np.where((n1 > 1e-30) & (n2 > 1e-30), n1 * n2, 1.0)
        c = np.einsum("ij,ij->i", e1, e2) / denom
        c = np.clip(c, -1.0, 1.0)
        return np.degrees(np.arccos(c))

    return np.stack(
        [_corner(A, B, C), _corner(B, A, C), _corner(C, A, B)],
        axis=1,
    )


def _triangle_aspect(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Aspect = longest_edge / (shortest_altitude). regular=1."""
    A = V[F[:, 0]]; B = V[F[:, 1]]; C = V[F[:, 2]]
    eab = np.linalg.norm(B - A, axis=1)
    ebc = np.linalg.norm(C - B, axis=1)
    eca = np.linalg.norm(A - C, axis=1)
    emax = np.maximum.reduce([eab, ebc, eca])
    area = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
    # altitude_min = 2·area / emax.
    h = 2.0 * area / np.where(emax > 1e-30, emax, 1.0)
    # inradius ≈ 2·area / (eab+ebc+eca).
    # aspect: emax / h.
    return np.where(h > 1e-30, emax / h, 1e6)


def surface_quality_report(
    pts: np.ndarray, tets: np.ndarray,
) -> SurfaceQualityReport:
    """tet boundary → triangle 품질 통계."""
    pts = np.asarray(pts, dtype=np.float64)
    tets = np.asarray(tets, dtype=np.int64)
    B = _tet_boundary_faces(tets)
    if B.shape[0] == 0:
        return SurfaceQualityReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    angs = _triangle_angles_deg(pts, B)
    asp = _triangle_aspect(pts, B)
    min_per_tri = angs.min(axis=1)
    return SurfaceQualityReport(
        n_faces=int(B.shape[0]),
        min_angle_deg=float(min_per_tri.min()),
        mean_min_angle_deg=float(min_per_tri.mean()),
        p5_min_angle_deg=float(np.percentile(min_per_tri, 5)),
        max_aspect=float(asp.max()),
        mean_aspect=float(asp.mean()),
        p95_aspect=float(np.percentile(asp, 95)),
    )
