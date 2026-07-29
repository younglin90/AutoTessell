"""Report-only certificates for a possible deterministic tet-core handoff."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class TetCoreCertificate:
    """The narrow contracts THex needs from an upstream tet complex."""

    stage: str
    n_tets: int
    n_boundary_faces: int
    strict_source_face_ratio: float
    boundary_source_face_ratio: float
    n_zero_volume: int
    n_negative_orientation: int
    missing_boundary_source_faces: tuple[tuple[int, int, int], ...]


def snapshot_tet_core_certificate(
    source_faces: np.ndarray,
    points: np.ndarray,
    tets: np.ndarray,
    stage: str,
    *,
    tolerance: float = 1e-12,
) -> TetCoreCertificate:
    """Measure source-face recovery and signed-volume validity without mutation."""
    from core.generator.native_tet.cdt_check import (
        cdt_face_ratio,
        check_edge_recovery,
    )
    from core.generator.native_tet.plane_coverage import _tet_boundary_faces

    cells = np.asarray(tets, dtype=np.int64)
    vertices = np.asarray(points, dtype=np.float64)
    source_keys = {
        tuple(int(vertex) for vertex in row)
        for row in np.sort(np.asarray(source_faces, dtype=np.int64), axis=1)
    }
    boundary_faces = _tet_boundary_faces(cells)
    boundary_keys = {
        tuple(int(vertex) for vertex in row) for row in np.sort(boundary_faces, axis=1)
    }
    missing_boundary_faces = tuple(sorted(source_keys - boundary_keys))
    face_ratio = float(cdt_face_ratio(check_edge_recovery(source_faces, cells)))
    boundary_ratio = (
        float(len(source_keys) - len(missing_boundary_faces)) / len(source_keys)
        if source_keys
        else 1.0
    )
    if len(cells) == 0:
        signed = np.empty(0, dtype=np.float64)
    else:
        local = vertices[cells]
        signed = (
            np.einsum(
                "ij,ij->i",
                local[:, 1] - local[:, 0],
                np.cross(local[:, 2] - local[:, 0], local[:, 3] - local[:, 0]),
            )
            / 6.0
        )
    report = TetCoreCertificate(
        stage=str(stage),
        n_tets=int(len(cells)),
        n_boundary_faces=int(len(boundary_faces)),
        strict_source_face_ratio=face_ratio,
        boundary_source_face_ratio=boundary_ratio,
        n_zero_volume=int(np.count_nonzero(np.abs(signed) <= tolerance)),
        n_negative_orientation=int(np.count_nonzero(signed < -tolerance)),
        missing_boundary_source_faces=missing_boundary_faces,
    )
    log.info(
        "native_tet_core_certificate",
        stage=report.stage,
        n_tets=report.n_tets,
        boundary_faces=report.n_boundary_faces,
        strict_source_face_ratio=round(report.strict_source_face_ratio, 6),
        boundary_source_face_ratio=round(report.boundary_source_face_ratio, 6),
        n_zero_volume=report.n_zero_volume,
        n_negative_orientation=report.n_negative_orientation,
        missing_boundary_source_faces=report.missing_boundary_source_faces[:8],
    )
    return report
