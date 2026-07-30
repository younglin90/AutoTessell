"""Final-array shape evidence for P4C replacement candidates."""

from __future__ import annotations

import numpy as np
import pytest

from core.generator.native_tet.mesher import _measure_final_shape_evidence_l0


def test_final_shape_evidence_is_measured_from_candidate_arrays() -> None:
    source = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float64
    )
    faces = np.asarray(
        ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)), dtype=np.int64
    )
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)

    plane_coverage, area_coverage, hausdorff_relative = (
        _measure_final_shape_evidence_l0(source, faces, source.copy(), tets)
    )

    assert plane_coverage == pytest.approx(1.0)
    assert area_coverage == pytest.approx(1.0)
    assert hausdorff_relative == pytest.approx(0.0, abs=1e-15)


def test_final_shape_evidence_exposes_a_displaced_output_corner() -> None:
    source = np.asarray(
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)), dtype=np.float64
    )
    faces = np.asarray(
        ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)), dtype=np.int64
    )
    candidate = source.copy()
    candidate[3, 2] += 0.25
    tets = np.asarray(((0, 1, 2, 3),), dtype=np.int64)

    _, area_coverage, hausdorff_relative = _measure_final_shape_evidence_l0(
        source, faces, candidate, tets
    )

    assert area_coverage < 1.0
    assert hausdorff_relative > 0.0
