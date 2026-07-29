"""TET-BCC-CERT-HARNESS: sampled split/wedge template dihedral floor (test-only)."""

from __future__ import annotations

import numpy as np

from core.generator.native_tet.quality import tet_min_dihedral_deg


def _regular_tet() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3) / 2, 0.0],
            [0.5, np.sqrt(3) / 6, np.sqrt(2.0 / 3.0)],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3]], dtype=np.int64)
    return pts, tets


def _bipyramid_template() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3) / 2, 0.0],
            [0.5, np.sqrt(3) / 6, 1.0e-2],
            [0.5, np.sqrt(3) / 6, -1.0],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 1, 2, 4]], dtype=np.int64)
    return pts, tets


def _near_coplanar_wedge_template() -> tuple[np.ndarray, np.ndarray]:
    pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.3, 0.3, 1.0e-4],
            [0.3, 0.6, -1.0e-4],
        ],
        dtype=np.float64,
    )
    tets = np.array([[0, 1, 2, 3], [0, 1, 3, 4], [0, 2, 3, 4]], dtype=np.int64)
    return pts, tets


def test_bcc_cert_harness_wedge_templates_have_positive_dihedral_floor() -> None:
    """샘플 템플릿에서 floor(최소 dihedral)가 0으로 떨어지면 즉시 fail."""
    templates = {
        "regular_tet": _regular_tet(),
        "bipyramid": _bipyramid_template(),
        "near_coplanar_wedge": _near_coplanar_wedge_template(),
    }
    floors: list[tuple[str, float]] = []
    for name, (pts, tets) in templates.items():
        min_dih = float(np.min(tet_min_dihedral_deg(pts, tets)))
        floors.append((name, min_dih))
        assert min_dih > 0.0, f"{name} template floor should not be zero: {min_dih}"

    assert min(f[1] for f in floors) > 0.0
